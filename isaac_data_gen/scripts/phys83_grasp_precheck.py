#!/usr/bin/env python3
"""Grasp-precheck action scan and official PickCube metric report for PHYS-8.3."""

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

from phys_data_gen.action_mapping import check_leisaac16_gripper_symmetry, command14_to_leisaac16
from phys_data_gen.image_validation import CAMERAS, mean_abs_diff
from phys_data_gen.logging_utils import log_environment, mark_fail, mark_pass, setup_logging
from phys_data_gen.phys8_tools import capture_multiview, policy_array, save_json, scene_metrics


def _make_scan_command(right_j1: float, right_j2: float, right_j4: float, right_j6: float, gripper: float):
    import numpy as np

    command = np.zeros((14,), dtype=np.float32)
    command[6] = 0.0
    command[7] = right_j1
    command[8] = right_j2
    command[10] = right_j4
    command[12] = right_j6
    command[13] = gripper
    return command


def _candidate_commands():
    # Conservative deterministic local scan around the right follower arm only.
    for right_j1 in (-0.28, -0.18, -0.08, 0.02):
        for right_j2 in (-0.30, -0.20, -0.10):
            for right_j4 in (0.00, 0.10, 0.20):
                yield _make_scan_command(right_j1, right_j2, right_j4, -0.08, 0.05)


def _step_action(env, action16, duration: int, session, stage_name: str):
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
    return obs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-name", default=None)
    parser.add_argument("--task", default="LeIsaac-XTrainer-PickCube-v0")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--num-envs", type=int, default=1)
    parser.add_argument("--seed", type=int, default=83)
    parser.add_argument("--candidate-steps", type=int, default=8)
    parser.add_argument("--settle-steps", type=int, default=16)
    args = parser.parse_args()

    session = setup_logging(session_name=args.session_name)
    session.run.info("phys83_grasp_precheck_start task=%s seed=%d", args.task, args.seed)
    log_environment(session, extra={"stage": "PHYS-8.3", "task": args.task, "seed": args.seed})

    from isaaclab.app import AppLauncher

    app_launcher = AppLauncher(headless=True, enable_cameras=True)
    simulation_app = app_launcher.app
    env = None
    result = 1

    try:
        import gymnasium as gym
        import numpy as np
        import torch
        from isaaclab_tasks.utils import parse_env_cfg
        import leisaac.tasks  # noqa: F401

        env_cfg = parse_env_cfg(args.task, device=args.device, num_envs=args.num_envs)
        env_cfg.use_teleop_device("bi_keyboard")
        env_cfg.recorders = None
        env_cfg.seed = args.seed
        if hasattr(env_cfg, "terminations") and hasattr(env_cfg.terminations, "time_out"):
            env_cfg.terminations.time_out = None
        for camera_name in ("stereo_left", "stereo_right"):
            if hasattr(env_cfg.scene, camera_name):
                setattr(env_cfg.scene, camera_name, None)
                session.run.info("disabled_scene_camera=%s", camera_name)

        env = gym.make(args.task, cfg=env_cfg).unwrapped
        session.run.info("gym_make_ok action_space=%s observation_space=%s", env.action_space, env.observation_space)
        obs, info = env.reset()
        env.sim.render()
        initial_images, initial_stats = capture_multiview(env, obs, "initial", session)
        initial_metrics = scene_metrics(env, obs)
        session.data.info("initial_metrics=%s", json.dumps(initial_metrics, sort_keys=True))

        candidate_results = []
        best = None
        for idx, command14 in enumerate(_candidate_commands()):
            action16 = command14_to_leisaac16(command14)
            obs = _step_action(env, action16, args.candidate_steps, session, f"scan_{idx:02d}")
            metrics = scene_metrics(env, obs)
            record = {
                "index": idx,
                "command14": command14.tolist(),
                "leisaac16": action16.tolist(),
                "metrics": metrics,
            }
            candidate_results.append(record)
            session.data.info("candidate=%d metrics=%s", idx, json.dumps(metrics, sort_keys=True))
            if best is None or metrics["right_grasp_center_to_cube_m"] < best["metrics"]["right_grasp_center_to_cube_m"]:
                best = record

        if best is None:
            raise RuntimeError("no scan candidates were evaluated")

        best_action16 = np.asarray(best["leisaac16"], dtype=np.float32)
        symmetry = check_leisaac16_gripper_symmetry(best_action16)
        if not symmetry.passed:
            raise RuntimeError(f"best candidate gripper symmetry failed: {symmetry}")
        obs = _step_action(env, best_action16, args.settle_steps, session, "best_approach_settle")
        approach_images, approach_stats = capture_multiview(env, obs, "best_approach", session)
        approach_metrics = scene_metrics(env, obs)

        close_command14 = np.asarray(best["command14"], dtype=np.float32)
        close_command14[13] = 1.0
        close_action16 = command14_to_leisaac16(close_command14)
        close_symmetry = check_leisaac16_gripper_symmetry(close_action16)
        if not close_symmetry.passed:
            raise RuntimeError(f"close gripper symmetry failed: {close_symmetry}")
        obs = _step_action(env, close_action16, args.settle_steps, session, "close_right_gripper")
        close_images, close_stats = capture_multiview(env, obs, "close_gripper", session)
        close_metrics = scene_metrics(env, obs)

        lift_command14 = close_command14.copy()
        lift_command14[8] -= 0.08
        lift_command14[10] += 0.08
        lift_action16 = command14_to_leisaac16(lift_command14)
        obs = _step_action(env, lift_action16, args.settle_steps, session, "lift_after_close")
        final_images, final_stats = capture_multiview(env, obs, "final_lift", session)
        final_metrics = scene_metrics(env, obs)

        observed_action = policy_array(obs, "actions").copy()
        action_error = float(np.max(np.abs(observed_action - lift_action16)))
        right_target = policy_array(obs, "right_joint_pos_target").copy()
        right_pos = policy_array(obs, "right_joint_pos_rel").copy()
        image_diffs = {camera_name: mean_abs_diff(initial_images[camera_name], final_images[camera_name]) for camera_name in CAMERAS}

        distance_improvement_m = float(initial_metrics["right_grasp_center_to_cube_m"] - best["metrics"]["right_grasp_center_to_cube_m"])
        issues = []
        if action_error > 1e-5:
            issues.append(f"observed action mismatch: {action_error}")
        if distance_improvement_m <= 0.005:
            issues.append(f"best approach did not improve distance enough: {distance_improvement_m}")
        if float(close_metrics["right_j2_8_m"]) <= 0.01:
            issues.append(f"right gripper did not close over official threshold: {close_metrics['right_j2_8_m']}")
        if max(image_diffs.values()) < 0.5:
            issues.append(f"image diff too small: {image_diffs}")

        report = {
            "stage": "PHYS-8.3",
            "task": args.task,
            "seed": args.seed,
            "initial_metrics": initial_metrics,
            "candidate_count": len(candidate_results),
            "candidate_results": candidate_results,
            "best_candidate": best,
            "approach_metrics": approach_metrics,
            "close_metrics": close_metrics,
            "final_metrics": final_metrics,
            "distance_improvement_m": distance_improvement_m,
            "observed_action_max_abs_error": action_error,
            "right_target_final": right_target.astype(float).tolist(),
            "right_position_final": right_pos.astype(float).tolist(),
            "image_diffs_initial_final": image_diffs,
            "official_summary": {
                "object_grasped": final_metrics["object_grasped_official"],
                "put_cube_to_plate": final_metrics["put_cube_to_plate_official"],
                "task_done": final_metrics["task_done_official"],
            },
            "precheck_passed": len(issues) == 0,
            "issues": issues,
        }
        save_json(session.root / "grasp_precheck_report.json", report)
        session.run.info("grasp_precheck_report_saved path=%s", session.root / "grasp_precheck_report.json")
        session.data.info("grasp_precheck_report=%s", json.dumps(report, sort_keys=True))

        if issues:
            mark_fail(session, "FAIL_PHYS83_GRASP_PRECHECK", "; ".join(issues))
            result = 10
        else:
            mark_pass(session, "PASS_PHYS83_GRASP_PRECHECK", "grasp precheck passed")
            session.run.info("phys83_grasp_precheck_ok")
            result = 0
    except BaseException as exc:
        session.run.error("phys83_grasp_precheck_failed type=%s error=%r", type(exc).__name__, exc)
        session.run.error("traceback:\n%s", traceback.format_exc())
        mark_fail(session, "FAIL_PHYS83_GRASP_PRECHECK", f"{type(exc).__name__}: {exc}")
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
