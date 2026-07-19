#!/usr/bin/env python3
"""Record a PHYS-8 grasp-precheck episode and generate a quality report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import traceback
from typing import Any

import h5py
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from phys_data_gen.action_mapping import check_leisaac16_gripper_symmetry, command14_to_leisaac16
from phys_data_gen.dataset_validation import render_markdown_report, validate_hdf5_dataset
from phys_data_gen.image_validation import CAMERAS, mean_abs_diff, save_multiview_grid
from phys_data_gen.logging_utils import log_environment, mark_fail, mark_pass, setup_logging
from phys_data_gen.phys8_tools import capture_multiview, make_command14, policy_array, save_json, scene_metrics


def _jsonable(value):
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, np.ndarray):
        return value.tolist()
    return value


def _load_best_command14(precheck_report: Path) -> tuple[np.ndarray, dict[str, Any]]:
    if not precheck_report.exists():
        raise FileNotFoundError(
            f"PHYS-8.3 precheck report not found: {precheck_report}. "
            "Run scripts/phys83_grasp_precheck.sh first."
        )
    report = json.loads(precheck_report.read_text(encoding="utf-8"))
    best = report.get("best_candidate", {})
    command14 = np.asarray(best.get("command14"), dtype=np.float32)
    if command14.shape != (14,):
        raise RuntimeError(f"invalid best command14 in {precheck_report}: shape={command14.shape}")
    if not report.get("precheck_passed", False):
        raise RuntimeError(f"PHYS-8.3 report did not pass precheck: {precheck_report}")
    return command14, report


def _step_action(env, action16: np.ndarray, duration: int, session, stage_name: str):
    import torch

    action_shape = env.action_space.shape
    action = torch.as_tensor(action16, dtype=torch.float32, device=env.device).reshape(1, -1).repeat(action_shape[0], 1)
    obs = None
    for local_step in range(duration):
        obs, reward, terminated, truncated, info = env.step(action)
        env.sim.render()
        session.data.info(
            "stage=%s local_step=%d action_max_abs=%.6f terminated=%s truncated=%s",
            stage_name,
            local_step,
            action.abs().max().detach().item(),
            terminated,
            truncated,
        )
    if obs is None:
        raise RuntimeError(f"stage {stage_name} did not run any steps")
    return obs


def _build_sequence(best_command14: np.ndarray) -> list[dict[str, Any]]:
    approach = best_command14.astype(np.float32).copy()
    approach[13] = min(float(approach[13]), 0.05)

    close = approach.copy()
    close[13] = 1.0

    lift = close.copy()
    lift[8] -= 0.08
    lift[10] += 0.08

    return [
        {"name": "open_hold", "steps": 8, "command14": make_command14("home_open")},
        {"name": "best_approach", "steps": 24, "command14": approach},
        {"name": "close_right_gripper", "steps": 18, "command14": close},
        {"name": "lift_after_close", "steps": 12, "command14": lift},
        {"name": "return_home_open", "steps": 8, "command14": make_command14("return_home_open")},
    ]


def _stamp_demo_attrs(dataset_path: Path, attrs: dict[str, Any]) -> list[str]:
    demos: list[str] = []
    with h5py.File(dataset_path, "a") as h5:
        data = h5["data"]
        for demo_name in sorted(k for k in data.keys() if k.startswith("demo_")):
            demo = data[demo_name]
            demos.append(demo_name)
            for key, value in attrs.items():
                if isinstance(value, (dict, list, tuple)):
                    demo.attrs[key] = json.dumps(value, sort_keys=True)
                elif value is None:
                    demo.attrs[key] = ""
                else:
                    demo.attrs[key] = value
    return demos


def _summarize_hdf5(dataset_path: Path, session) -> dict[str, Any]:
    summary: dict[str, Any] = {"path": str(dataset_path), "bytes": dataset_path.stat().st_size, "demos": []}
    with h5py.File(dataset_path, "r") as h5:
        for demo_name in sorted(k for k in h5["data"].keys() if k.startswith("demo_")):
            demo = h5["data"][demo_name]
            actions = np.asarray(demo["actions"])
            symmetry = check_leisaac16_gripper_symmetry(actions)
            demo_summary: dict[str, Any] = {
                "name": demo_name,
                "attrs": {k: _jsonable(v) for k, v in demo.attrs.items()},
                "num_samples": int(demo.attrs.get("num_samples", actions.shape[0])),
                "action_shape": list(actions.shape),
                "action_min": float(np.min(actions)),
                "action_max": float(np.max(actions)),
                "action_mean_abs": float(np.mean(np.abs(actions))),
                "gripper_symmetry": {
                    "passed": symmetry.passed,
                    "left_max_abs": symmetry.left_max_abs,
                    "right_max_abs": symmetry.right_max_abs,
                },
                "images": {},
            }
            first_images: dict[str, np.ndarray] = {}
            last_images: dict[str, np.ndarray] = {}
            for camera_name in CAMERAS:
                key = f"obs/{camera_name}"
                data = demo[key]
                first = np.asarray(data[0])
                last = np.asarray(data[-1])
                first_images[camera_name] = first
                last_images[camera_name] = last
                demo_summary["images"][key] = {
                    "shape": list(data.shape),
                    "dtype": str(data.dtype),
                    "first_std": float(np.std(first)),
                    "last_std": float(np.std(last)),
                    "first_last_mean_abs_diff": mean_abs_diff(first, last),
                }
            save_multiview_grid(first_images, session.root / f"{demo_name}_hdf5_first_grid.png", title=f"{demo_name}_hdf5_first")
            save_multiview_grid(last_images, session.root / f"{demo_name}_hdf5_last_grid.png", title=f"{demo_name}_hdf5_last")
            summary["demos"].append(demo_summary)
    summary["total_samples"] = int(sum(d["num_samples"] for d in summary["demos"]))
    return summary


def _render_markdown(report: dict[str, Any]) -> str:
    official = report["official_summary"]
    lines = [
        "# PHYS-8.4 Episode Quality Report",
        "",
        f"- Status: `{report['status']}`",
        f"- Dataset: `{report['dataset_file']}`",
        f"- Samples: `{report['hdf5']['total_samples']}`",
        f"- Validator passed: `{report['validator']['passed']}`",
        f"- Official object_grasped: `{official['object_grasped']}`",
        f"- Official put_cube_to_plate: `{official['put_cube_to_plate']}`",
        f"- Official task_done: `{official['task_done']}`",
        f"- Training success sample: `{report['training_success_sample']}`",
        "",
        "## Sequence",
        "",
        "| Stage | Steps | Command14 |",
        "|---|---:|---|",
    ]
    for stage in report["sequence"]:
        cmd = ", ".join(f"{v:.4f}" for v in stage["command14"])
        lines.append(f"| `{stage['name']}` | `{stage['steps']}` | `{cmd}` |")

    lines.extend(
        [
            "",
            "## HDF5",
            "",
            "| Demo | Samples | Action Min | Action Max | Action Mean Abs | Gripper Symmetry |",
            "|---|---:|---:|---:|---:|---|",
        ]
    )
    for demo in report["hdf5"]["demos"]:
        sym = demo["gripper_symmetry"]
        lines.append(
            f"| `{demo['name']}` | `{demo['num_samples']}` | `{demo['action_min']:.5f}` | "
            f"`{demo['action_max']:.5f}` | `{demo['action_mean_abs']:.5f}` | `{sym['passed']}` |"
        )

    lines.extend(["", "## Image Checks", "", "| Demo | Camera | Shape | First Std | Last Std | First/Last Diff |", "|---|---|---:|---:|---:|---:|"])
    for demo in report["hdf5"]["demos"]:
        for key, meta in demo["images"].items():
            lines.append(
                f"| `{demo['name']}` | `{key}` | `{meta['shape']}` | `{meta['first_std']:.5f}` | "
                f"`{meta['last_std']:.5f}` | `{meta['first_last_mean_abs_diff']:.5f}` |"
            )

    lines.extend(["", "## Limitations", ""])
    if report["training_success_sample"]:
        lines.append("- This episode meets the current official task success flag.")
    else:
        lines.append("- This episode is a recorded control/quality sample, not a formal successful grasp training sample.")
        lines.append("- Next improvement should target IK/policy/teleop alignment to satisfy official PickCube success, not random patching.")

    lines.extend(["", "## Issues", ""])
    if report["issues"]:
        for issue in report["issues"]:
            lines.append(f"- {issue}")
    else:
        lines.append("- No recording or schema quality issues.")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-name", default=None)
    parser.add_argument("--task", default="LeIsaac-XTrainer-PickCube-v0")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--num-envs", type=int, default=1)
    parser.add_argument("--seed", type=int, default=84)
    parser.add_argument("--dataset-file", default="datasets/raw_hdf5/pickcube_episode_phys84.hdf5")
    parser.add_argument("--precheck-report", default="logs/session_phys83_grasp_precheck_v1/grasp_precheck_report.json")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    session = setup_logging(session_name=args.session_name)
    dataset_path = (ROOT / args.dataset_file).resolve() if not Path(args.dataset_file).is_absolute() else Path(args.dataset_file)
    precheck_report_path = (ROOT / args.precheck_report).resolve() if not Path(args.precheck_report).is_absolute() else Path(args.precheck_report)
    session.run.info("phys84_episode_record_quality_start task=%s dataset=%s", args.task, dataset_path)
    log_environment(
        session,
        extra={
            "stage": "PHYS-8.4",
            "task": args.task,
            "seed": args.seed,
            "dataset_file": str(dataset_path),
            "precheck_report": str(precheck_report_path),
        },
    )

    if dataset_path.exists():
        if args.overwrite:
            dataset_path.unlink()
            session.run.info("removed_existing_dataset=%s", dataset_path)
        else:
            session.run.error("dataset_exists=%s", dataset_path)
            return 3
    dataset_path.parent.mkdir(parents=True, exist_ok=True)

    from isaaclab.app import AppLauncher

    app_launcher = AppLauncher(headless=True, enable_cameras=True)
    simulation_app = app_launcher.app
    env = None
    result = 1

    try:
        import gymnasium as gym
        import torch
        from isaaclab.envs import ManagerBasedRLEnv
        from isaaclab.managers import DatasetExportMode, TerminationTermCfg
        from isaaclab_tasks.utils import parse_env_cfg
        import leisaac.tasks  # noqa: F401
        from leisaac.enhance.managers import StreamingRecorderManager

        best_command14, precheck_report = _load_best_command14(precheck_report_path)
        sequence = _build_sequence(best_command14)
        for stage in sequence:
            action16 = command14_to_leisaac16(stage["command14"])
            symmetry = check_leisaac16_gripper_symmetry(action16)
            if not symmetry.passed:
                raise RuntimeError(f"{stage['name']} gripper symmetry failed: {symmetry}")
            stage["leisaac16"] = action16
            session.data.info("sequence_stage=%s command14=%s leisaac16=%s", stage["name"], stage["command14"], action16)

        env_cfg = parse_env_cfg(args.task, device=args.device, num_envs=args.num_envs)
        env_cfg.use_teleop_device("bi_keyboard")
        env_cfg.seed = args.seed
        if hasattr(env_cfg, "terminations") and hasattr(env_cfg.terminations, "time_out"):
            env_cfg.terminations.time_out = None
        if hasattr(env_cfg, "terminations"):
            env_cfg.terminations.success = TerminationTermCfg(
                func=lambda env: torch.zeros(env.num_envs, dtype=torch.bool, device=env.device)
            )
        for camera_name in ("stereo_left", "stereo_right"):
            if hasattr(env_cfg.scene, camera_name):
                setattr(env_cfg.scene, camera_name, None)
                session.run.info("disabled_scene_camera=%s", camera_name)

        env_cfg.recorders.dataset_export_mode = DatasetExportMode.EXPORT_ALL
        env_cfg.recorders.dataset_export_dir_path = str(dataset_path.parent)
        env_cfg.recorders.dataset_filename = dataset_path.stem

        env = gym.make(args.task, cfg=env_cfg).unwrapped
        if not isinstance(env, ManagerBasedRLEnv):
            session.run.warning("env_type=%s", type(env).__name__)
        del env.recorder_manager
        env.recorder_manager = StreamingRecorderManager(env_cfg.recorders, env)
        env.recorder_manager.flush_steps = max(sum(stage["steps"] for stage in sequence) + 1, 120)
        env.recorder_manager.compression = "lzf"

        obs, info = env.reset()
        env.sim.render()
        initial_images, initial_stats = capture_multiview(env, obs, "record_initial", session)
        initial_metrics = scene_metrics(env, obs)
        stage_metrics: dict[str, Any] = {"initial": initial_metrics}
        stage_image_stats: dict[str, Any] = {"initial": initial_stats}
        session.data.info("initial_metrics=%s", json.dumps(initial_metrics, sort_keys=True))

        obs_by_stage = {}
        for stage in sequence:
            obs = _step_action(env, stage["leisaac16"], int(stage["steps"]), session, stage["name"])
            metrics = scene_metrics(env, obs)
            stage_metrics[stage["name"]] = metrics
            obs_by_stage[stage["name"]] = obs
            session.data.info("stage=%s metrics=%s", stage["name"], json.dumps(metrics, sort_keys=True))
            if stage["name"] in {"best_approach", "close_right_gripper", "lift_after_close", "return_home_open"}:
                _, stats = capture_multiview(env, obs, f"record_{stage['name']}", session)
                stage_image_stats[stage["name"]] = stats

        final_obs = obs_by_stage["return_home_open"]
        final_metrics = stage_metrics["return_home_open"]
        observed_action = policy_array(final_obs, "actions").copy()
        expected_final_action = command14_to_leisaac16(make_command14("return_home_open"))
        final_action_error = float(np.max(np.abs(observed_action - expected_final_action)))

        env.recorder_manager.export_episodes(from_step=False)
        session.run.info(
            "recorder_exported successful=%s failed=%s",
            env.recorder_manager.exported_successful_episode_count,
            getattr(env.recorder_manager, "exported_failed_episode_count", "unavailable"),
        )

        if env is not None:
            env.close()
            env = None

        official_summary = {
            "object_grasped": bool(final_metrics["object_grasped_official"]),
            "put_cube_to_plate": bool(final_metrics["put_cube_to_plate_official"]),
            "task_done": bool(final_metrics["task_done_official"]),
            "lift_stage_object_grasped": bool(stage_metrics["lift_after_close"]["object_grasped_official"]),
            "lift_stage_right_grasp_center_to_cube_m": float(stage_metrics["lift_after_close"]["right_grasp_center_to_cube_m"]),
            "lift_stage_right_j2_8_m": float(stage_metrics["lift_after_close"]["right_j2_8_m"]),
        }
        demo_names = _stamp_demo_attrs(
            dataset_path,
            {
                "stage": "PHYS-8.4",
                "seed": args.seed,
                "task": args.task,
                "success": bool(official_summary["task_done"]),
                "object_grasped_official": bool(official_summary["object_grasped"]),
                "put_cube_to_plate_official": bool(official_summary["put_cube_to_plate"]),
                "task_done_official": bool(official_summary["task_done"]),
                "precheck_report": str(precheck_report_path),
                "sequence": [
                    {"name": stage["name"], "steps": int(stage["steps"]), "command14": np.asarray(stage["command14"]).astype(float).tolist()}
                    for stage in sequence
                ],
            },
        )
        session.run.info("hdf5_attrs_stamped demos=%s", demo_names)

        validation_result = validate_hdf5_dataset(dataset_path, require_success=False)
        validator_dict = validation_result.to_dict()
        (session.root / "dataset_validation_report.json").write_text(
            json.dumps(validator_dict, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (session.root / "dataset_validation_report.md").write_text(render_markdown_report(validation_result), encoding="utf-8")

        hdf5_summary = _summarize_hdf5(dataset_path, session)
        issues: list[str] = []
        if not validation_result.passed:
            issues.append("HDF5 validator failed")
        if final_action_error > 1e-5:
            issues.append(f"final observed action mismatch: {final_action_error}")
        if hdf5_summary["total_samples"] <= 0:
            issues.append("recorded zero HDF5 samples")
        for demo in hdf5_summary["demos"]:
            if not demo["gripper_symmetry"]["passed"]:
                issues.append(f"{demo['name']} gripper symmetry failed")
            if demo["action_mean_abs"] <= 0.001:
                issues.append(f"{demo['name']} actions are effectively zero")
            max_diff = max(meta["first_last_mean_abs_diff"] for meta in demo["images"].values())
            if max_diff < 0.5:
                issues.append(f"{demo['name']} HDF5 first/last image diff too small: {max_diff}")
            for camera, meta in demo["images"].items():
                if meta["first_std"] < 2.0 or meta["last_std"] < 2.0:
                    issues.append(f"{demo['name']} {camera} image std too low")

        report = {
            "stage": "PHYS-8.4",
            "status": "FAIL" if issues else "PASS",
            "task": args.task,
            "seed": args.seed,
            "dataset_file": str(dataset_path),
            "precheck_report": str(precheck_report_path),
            "precheck_official_summary": precheck_report.get("official_summary", {}),
            "sequence": [
                {
                    "name": stage["name"],
                    "steps": int(stage["steps"]),
                    "command14": np.asarray(stage["command14"]).astype(float).tolist(),
                    "leisaac16": np.asarray(stage["leisaac16"]).astype(float).tolist(),
                }
                for stage in sequence
            ],
            "stage_metrics": stage_metrics,
            "stage_image_stats": stage_image_stats,
            "official_summary": official_summary,
            "training_success_sample": bool(official_summary["task_done"]),
            "final_observed_action_max_abs_error": final_action_error,
            "validator": validator_dict,
            "hdf5": hdf5_summary,
            "issues": issues,
        }
        save_json(session.root / "episode_quality_report.json", report)
        (session.root / "episode_quality_report.md").write_text(_render_markdown(report), encoding="utf-8")
        session.data.info("episode_quality_report=%s", json.dumps(report, sort_keys=True))

        if issues:
            mark_fail(session, "FAIL_PHYS84_EPISODE_RECORD_QUALITY", "; ".join(issues))
            result = 10
        else:
            mark_pass(session, "PASS_PHYS84_EPISODE_RECORD_QUALITY", "episode recording and quality report passed")
            session.run.info("phys84_episode_record_quality_ok")
            result = 0
    except BaseException as exc:
        session.run.error("phys84_episode_record_quality_failed type=%s error=%r", type(exc).__name__, exc)
        session.run.error("traceback:\n%s", traceback.format_exc())
        mark_fail(session, "FAIL_PHYS84_EPISODE_RECORD_QUALITY", f"{type(exc).__name__}: {exc}")
        result = 20
    finally:
        if env is not None:
            try:
                env.close()
            except Exception as exc:
                session.run.warning("env_close_warning=%r", exc)
        try:
            simulation_app.close(wait_for_replicator=False, skip_cleanup=True)
        except TypeError:
            simulation_app.close()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
