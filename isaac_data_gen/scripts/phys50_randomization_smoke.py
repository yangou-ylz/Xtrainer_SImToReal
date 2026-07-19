#!/usr/bin/env python3
"""Validate minimal PickCube object-pose randomization without cameras."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import traceback


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from phys_data_gen.logging_utils import log_environment, mark_fail, mark_pass, setup_logging


EXPECTED_BASE = {
    "cube": {"x": 0.5, "y": 0.0, "z": 0.1},
    "Plate": {"x": 0.7, "y": 0.0, "z": 0.1},
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-name", default=None)
    parser.add_argument("--task", default="LeIsaac-XTrainer-PickCube-v0")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--num-envs", type=int, default=1)
    parser.add_argument("--seeds", default="50,51,52,53,54")
    parser.add_argument("--xy-limit", type=float, default=0.031)
    parser.add_argument("--z-tolerance", type=float, default=0.003)
    parser.add_argument("--min-variation", type=float, default=0.002)
    args = parser.parse_args()

    seeds = [int(item.strip()) for item in args.seeds.split(",") if item.strip()]
    session = setup_logging(session_name=args.session_name)
    session.run.info("phys50_randomization_start task=%s seeds=%s", args.task, seeds)
    log_environment(
        session,
        extra={
            "stage": "PHYS-5.0",
            "task": args.task,
            "seeds": seeds,
            "profile": "minimal_pickcube",
        },
    )

    from isaaclab.app import AppLauncher

    app_launcher = AppLauncher(headless=True)
    simulation_app = app_launcher.app
    env = None
    result = 1

    try:
        import gymnasium as gym
        import torch
        from isaaclab_tasks.utils import parse_env_cfg
        import leisaac.tasks  # noqa: F401

        env_cfg = parse_env_cfg(args.task, device=args.device, num_envs=args.num_envs)
        env_cfg.use_teleop_device("bi_keyboard")
        env_cfg.recorders = None
        env_cfg.seed = seeds[0]
        if hasattr(env_cfg, "terminations") and hasattr(env_cfg.terminations, "time_out"):
            env_cfg.terminations.time_out = None

        for camera_name in ("left_wrist", "right_wrist", "top", "stereo_left", "stereo_right"):
            if hasattr(env_cfg.scene, camera_name):
                setattr(env_cfg.scene, camera_name, None)
                session.run.info("disabled_scene_camera=%s", camera_name)
        policy_obs = getattr(getattr(env_cfg, "observations", None), "policy", None)
        if policy_obs is not None:
            for obs_name in ("left_wrist", "right_wrist", "top"):
                if hasattr(policy_obs, obs_name):
                    setattr(policy_obs, obs_name, None)
                    session.run.info("disabled_camera_observation=%s", obs_name)

        env = gym.make(args.task, cfg=env_cfg).unwrapped
        action = torch.zeros(env.action_space.shape, device=env.device)
        samples: list[dict[str, object]] = []

        for seed in seeds:
            obs, info = env.reset(seed=seed)
            env.step(action)
            env.scene.update(env.step_dt)
            env_origin = env.scene.env_origins[0].detach().cpu()
            sample = {"seed": seed, "objects": {}}
            for name in ("cube", "Plate"):
                obj = env.scene[name]
                pos = (obj.data.root_pos_w[0].detach().cpu() - env_origin).tolist()
                base = EXPECTED_BASE[name]
                offsets = {
                    "x": float(pos[0] - base["x"]),
                    "y": float(pos[1] - base["y"]),
                    "z": float(pos[2] - base["z"]),
                }
                sample["objects"][name] = {
                    "pos": [float(v) for v in pos],
                    "offset": offsets,
                }
            samples.append(sample)
            session.data.info("randomization_sample=%s", json.dumps(sample, sort_keys=True))

        issues: list[str] = []
        for name in ("cube", "Plate"):
            x_offsets = [sample["objects"][name]["offset"]["x"] for sample in samples]
            y_offsets = [sample["objects"][name]["offset"]["y"] for sample in samples]
            z_positions = [sample["objects"][name]["pos"][2] for sample in samples]
            for axis, values, limit in (
                ("x", x_offsets, args.xy_limit),
                ("y", y_offsets, args.xy_limit),
            ):
                max_abs = max(abs(v) for v in values)
                if max_abs > limit:
                    issues.append(f"{name}.{axis} max_abs_offset {max_abs:.6f} exceeds {limit:.6f}")
            xy_variation = max(max(x_offsets) - min(x_offsets), max(y_offsets) - min(y_offsets))
            if xy_variation < args.min_variation:
                issues.append(f"{name} xy variation {xy_variation:.6f} below {args.min_variation:.6f}")
            z_variation = max(z_positions) - min(z_positions)
            if z_variation > args.z_tolerance:
                issues.append(f"{name}.z variation {z_variation:.6f} exceeds {args.z_tolerance:.6f}")

        report = {
            "status": "FAIL" if issues else "PASS",
            "profile": "minimal_pickcube",
            "expected_ranges": {
                "cube": {"x": [-0.03, 0.03], "y": [-0.03, 0.03], "z": [0.0, 0.0]},
                "Plate": {"x": [-0.03, 0.03], "y": [-0.03, 0.03], "z": [0.0, 0.0]},
            },
            "samples": samples,
            "issues": issues,
        }
        report_json = session.root / "randomization_report.json"
        report_md = session.root / "randomization_report.md"
        report_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        report_md.write_text(render_report(report), encoding="utf-8")
        session.run.info("randomization_report=%s", report_md)
        session.data.info("randomization_summary=%s", json.dumps(report, sort_keys=True))

        if issues:
            mark_fail(session, "FAIL_PHYS50_RANDOMIZATION_SMOKE", "; ".join(issues))
            result = 10
        else:
            mark_pass(session, "PASS_PHYS50_RANDOMIZATION_SMOKE", "minimal PickCube randomization smoke passed")
            session.run.info("phys50_randomization_ok")
            result = 0
    except BaseException as exc:
        session.run.error("phys50_randomization_failed type=%s error=%r", type(exc).__name__, exc)
        session.run.error("traceback:\n%s", traceback.format_exc())
        mark_fail(session, "FAIL_PHYS50_RANDOMIZATION_SMOKE", f"{type(exc).__name__}: {exc}")
        result = 20
    finally:
        if env is not None:
            try:
                env.close()
            except Exception as exc:
                session.run.warning("env_close_warning=%r", exc)
        if result in (0, 10):
            try:
                simulation_app.close(wait_for_replicator=False, skip_cleanup=True)
            except TypeError:
                simulation_app.close()
        else:
            session.run.error("skip_simulation_app_close_after_failure_to_preserve_traceback")
    return result


def render_report(report: dict) -> str:
    lines = [
        "# PHYS-5.0 Randomization Smoke Report",
        "",
        f"- Status: `{report['status']}`",
        f"- Profile: `{report['profile']}`",
        "",
        "## Samples",
        "",
        "| Seed | Object | X | Y | Z | dX | dY | dZ |",
        "|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for sample in report["samples"]:
        for name, meta in sample["objects"].items():
            pos = meta["pos"]
            offset = meta["offset"]
            lines.append(
                f"| `{sample['seed']}` | `{name}` | `{pos[0]:.5f}` | `{pos[1]:.5f}` | `{pos[2]:.5f}` | "
                f"`{offset['x']:.5f}` | `{offset['y']:.5f}` | `{offset['z']:.5f}` |"
            )
    lines.extend(["", "## Issues", ""])
    if report["issues"]:
        for issue in report["issues"]:
            lines.append(f"- {issue}")
    else:
        lines.append("No issues.")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
