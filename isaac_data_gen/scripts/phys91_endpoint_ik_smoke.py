#!/usr/bin/env python3
"""Validate right-arm endpoint-pose control through LeIsaac xtrainer_vr Differential IK."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import traceback
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from phys_data_gen.image_validation import CAMERAS, mean_abs_diff
from phys_data_gen.logging_utils import log_environment, mark_pass, setup_logging
from phys_data_gen.phys8_tools import capture_multiview, policy_array, save_json, tensor_to_numpy


def _quat_wxyz_from_euler_xyz_deg(roll: float, pitch: float, yaw: float) -> np.ndarray:
    from scipy.spatial.transform import Rotation as R

    xyzw = R.from_euler("XYZ", [roll, pitch, yaw], degrees=True).as_quat()
    return np.asarray([xyzw[3], xyzw[0], xyzw[1], xyzw[2]], dtype=np.float32)


def _home_pose(hand: str) -> tuple[np.ndarray, np.ndarray]:
    if hand == "left":
        return (
            np.asarray([0.345, -0.1175, 0.4157], dtype=np.float32),
            _quat_wxyz_from_euler_xyz_deg(180.0, 0.0, 90.0),
        )
    if hand == "right":
        return (
            np.asarray([0.715, -0.1175, 0.4157], dtype=np.float32),
            _quat_wxyz_from_euler_xyz_deg(-180.0, 0.0, -90.0),
        )
    raise ValueError(f"unknown hand: {hand}")


def _make_xtrainer_vr_action(
    *,
    right_pos_delta: tuple[float, float, float] = (0.0, 0.0, 0.0),
    right_rpy_delta_deg: tuple[float, float, float] = (0.0, 0.0, 0.0),
    right_gripper: float = 0.0,
    left_gripper: float = 0.0,
) -> np.ndarray:
    """Return 18-D xtrainer_vr action: left pose7+grip2, right pose7+grip2."""

    left_pos, left_quat = _home_pose("left")
    right_pos, _ = _home_pose("right")
    right_pos = right_pos + np.asarray(right_pos_delta, dtype=np.float32)

    # Keep right home orientation as the base, then apply a small explicit delta for smoke coverage.
    base_rpy = np.asarray([-180.0, 0.0, -90.0], dtype=np.float32)
    right_quat = _quat_wxyz_from_euler_xyz_deg(*(base_rpy + np.asarray(right_rpy_delta_deg, dtype=np.float32)))

    action = np.zeros((18,), dtype=np.float32)
    action[0:3] = left_pos
    action[3:7] = left_quat
    action[7] = 0.0
    action[8] = 0.04 * float(left_gripper)
    action[9:12] = right_pos
    action[12:16] = right_quat
    action[16] = 0.0
    action[17] = 0.04 * float(right_gripper)
    # LeIsaac xtrainer_vr maps gripper scalars to symmetric prismatic pair. For raw env action,
    # provide the same sign convention expected by JointPositionActionCfg ordering.
    action[7] = -action[8]
    action[16] = -action[17]
    return action


def _first_env(value) -> np.ndarray:
    array = tensor_to_numpy(value)
    if array.ndim >= 2 and array.shape[0] == 1:
        return array[0]
    return array


def _right_eef_state(env) -> dict[str, Any]:
    frame = env.scene["right_ee_frame"]
    pos = _first_env(frame.data.target_pos_w)
    quat = _first_env(frame.data.target_quat_w)
    return {
        "right_flange_pos_w": pos[0].astype(float).tolist(),
        "right_grasp_center_pos_w": pos[1].astype(float).tolist() if pos.shape[0] > 1 else pos[0].astype(float).tolist(),
        "right_flange_quat_w": quat[0].astype(float).tolist(),
    }


def _step_action(env, action_np: np.ndarray, steps: int, session, stage_name: str):
    import torch

    action_shape = env.action_space.shape
    action = torch.as_tensor(action_np, dtype=torch.float32, device=env.device).reshape(1, -1).repeat(action_shape[0], 1)
    obs = None
    for local_step in range(steps):
        obs, reward, terminated, truncated, info = env.step(action)
        env.sim.render()
        session.data.info(
            "stage=%s local_step=%d action_shape=%s action_max_abs=%.6f terminated=%s truncated=%s",
            stage_name,
            local_step,
            tuple(action.shape),
            action.abs().max().detach().item(),
            terminated,
            truncated,
        )
    if obs is None:
        raise RuntimeError(f"stage {stage_name} did not step")
    return obs


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# PHYS-9.1 Endpoint IK Smoke Report",
        "",
        f"- Status: `{report['status']}`",
        f"- Task: `{report['task']}`",
        f"- Action shape: `{report['action_space_shape']}`",
        f"- Right flange displacement: `{report['right_flange_displacement_m']:.6f} m`",
        f"- Right joint target delta: `{report['right_joint_target_delta_max_abs']:.6f}`",
        f"- Max image diff: `{report['max_image_diff']:.6f}`",
        "",
        "## Sequence",
        "",
        "| Stage | Steps | Right xyz delta | Right rpy delta deg | Gripper |",
        "|---|---:|---|---|---:|",
    ]
    for stage in report["sequence"]:
        lines.append(
            f"| `{stage['name']}` | `{stage['steps']}` | `{stage['right_pos_delta']}` | "
            f"`{stage['right_rpy_delta_deg']}` | `{stage['right_gripper']}` |"
        )
    lines.extend(["", "## Issues", ""])
    if report["issues"]:
        for issue in report["issues"]:
            lines.append(f"- {issue}")
    else:
        lines.append("- No endpoint IK smoke issues.")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-name", default=None)
    parser.add_argument("--task", default="LeIsaac-XTrainer-PickCube-v0")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--num-envs", type=int, default=1)
    parser.add_argument("--seed", type=int, default=91)
    args = parser.parse_args()

    session = setup_logging(session_name=args.session_name)
    session.run.info("phys91_endpoint_ik_smoke_start task=%s seed=%d", args.task, args.seed)
    log_environment(session, extra={"stage": "PHYS-9.1", "task": args.task, "seed": args.seed})

    from isaaclab.app import AppLauncher

    app_launcher = AppLauncher(headless=True, enable_cameras=True)
    simulation_app = app_launcher.app
    env = None
    result = 1

    try:
        import gymnasium as gym
        from isaaclab_tasks.utils import parse_env_cfg
        import leisaac.tasks  # noqa: F401

        env_cfg = parse_env_cfg(args.task, device=args.device, num_envs=args.num_envs)
        env_cfg.use_teleop_device("xtrainer_vr")
        env_cfg.recorders = None
        env_cfg.seed = args.seed
        if hasattr(env_cfg, "terminations") and hasattr(env_cfg.terminations, "time_out"):
            env_cfg.terminations.time_out = None
        if hasattr(env_cfg, "terminations") and hasattr(env_cfg.terminations, "success"):
            env_cfg.terminations.success = None
        for camera_name in ("stereo_left", "stereo_right"):
            if hasattr(env_cfg.scene, camera_name):
                setattr(env_cfg.scene, camera_name, None)
                session.run.info("disabled_scene_camera=%s", camera_name)

        env = gym.make(args.task, cfg=env_cfg).unwrapped
        session.run.info("gym_make_ok action_space=%s observation_space=%s", env.action_space, env.observation_space)
        obs, info = env.reset()
        env.sim.render()
        action_shape = env.action_space.shape
        if len(action_shape) != 2 or action_shape[-1] != 18:
            raise RuntimeError(f"unexpected xtrainer_vr action_space shape {action_shape}; expected (*, 18)")

        before_images, before_stats = capture_multiview(env, obs, "initial", session)
        before_eef = _right_eef_state(env)
        before_right_target = policy_array(obs, "right_joint_pos_target").copy()
        before_right_pos = policy_array(obs, "right_joint_pos_rel").copy()

        sequence = [
            {"name": "home_open", "steps": 16, "right_pos_delta": [0.0, 0.0, 0.0], "right_rpy_delta_deg": [0.0, 0.0, 0.0], "right_gripper": 0.0},
            {"name": "x_plus", "steps": 28, "right_pos_delta": [0.035, 0.0, 0.0], "right_rpy_delta_deg": [0.0, 0.0, 0.0], "right_gripper": 0.0},
            {"name": "z_plus_yaw", "steps": 28, "right_pos_delta": [0.035, 0.0, 0.035], "right_rpy_delta_deg": [0.0, 0.0, 8.0], "right_gripper": 0.0},
            {"name": "close", "steps": 16, "right_pos_delta": [0.035, 0.0, 0.035], "right_rpy_delta_deg": [0.0, 0.0, 8.0], "right_gripper": 1.0},
        ]
        sent_actions: list[dict[str, Any]] = []
        for stage in sequence:
            action_np = _make_xtrainer_vr_action(
                right_pos_delta=tuple(stage["right_pos_delta"]),
                right_rpy_delta_deg=tuple(stage["right_rpy_delta_deg"]),
                right_gripper=float(stage["right_gripper"]),
            )
            obs = _step_action(env, action_np, int(stage["steps"]), session, stage["name"])
            sent_actions.append({"stage": stage["name"], "action18": action_np.astype(float).tolist()})

        final_images, final_stats = capture_multiview(env, obs, "final", session)
        after_eef = _right_eef_state(env)
        after_right_target = policy_array(obs, "right_joint_pos_target").copy()
        after_right_pos = policy_array(obs, "right_joint_pos_rel").copy()
        observed_action = policy_array(obs, "actions").copy()

        image_diffs = {camera: mean_abs_diff(before_images[camera], final_images[camera]) for camera in CAMERAS}
        right_flange_displacement = float(
            np.linalg.norm(
                np.asarray(after_eef["right_flange_pos_w"], dtype=np.float64)
                - np.asarray(before_eef["right_flange_pos_w"], dtype=np.float64)
            )
        )
        target_delta = float(np.max(np.abs(after_right_target - before_right_target)))
        pos_delta = float(np.max(np.abs(after_right_pos - before_right_pos)))
        issues: list[str] = []
        if not np.all(np.isfinite(observed_action)):
            issues.append("observed action contains NaN or Inf")
        if not np.all(np.isfinite(after_right_target)) or not np.all(np.isfinite(after_right_pos)):
            issues.append("right joint observations contain NaN or Inf")
        if right_flange_displacement < 0.01:
            issues.append(f"right flange displacement too small: {right_flange_displacement:.6f} m")
        if target_delta < 0.01:
            issues.append(f"right joint target delta too small: {target_delta:.6f}")
        if pos_delta < 0.001:
            issues.append(f"right joint position delta too small: {pos_delta:.6f}")
        if max(image_diffs.values()) < 0.2:
            issues.append(f"image diff too small: {image_diffs}")

        report = {
            "status": "PASS" if not issues else "FAIL",
            "stage": "PHYS-9.1",
            "task": args.task,
            "seed": args.seed,
            "action_space_shape": list(action_shape),
            "sequence": sequence,
            "sent_actions": sent_actions,
            "before_eef": before_eef,
            "after_eef": after_eef,
            "right_flange_displacement_m": right_flange_displacement,
            "right_joint_target_delta_max_abs": target_delta,
            "right_joint_position_delta_max_abs": pos_delta,
            "observed_action_shape": list(observed_action.shape),
            "observed_action_max_abs": float(np.max(np.abs(observed_action))),
            "image_diffs_initial_final": image_diffs,
            "max_image_diff": float(max(image_diffs.values())),
            "initial_stats": before_stats,
            "final_stats": final_stats,
            "issues": issues,
        }
        save_json(session.root / "endpoint_ik_report.json", report)
        (session.root / "endpoint_ik_report.md").write_text(_render_markdown(report), encoding="utf-8")
        session.data.info("endpoint_ik_report=%s", json.dumps(report, sort_keys=True))

        if issues:
            fail_marker = session.root / "FAIL_PHYS91_ENDPOINT_IK_SMOKE"
            fail_marker.write_text("; ".join(issues) + "\n", encoding="utf-8")
            raise RuntimeError("PHYS-9.1 endpoint IK smoke failed: " + "; ".join(issues))
        mark_pass(session, "PASS_PHYS91_ENDPOINT_IK_SMOKE", "PHYS-9.1 endpoint IK smoke passed")
        result = 0
    except BaseException as exc:
        session.run.error("phys91_endpoint_ik_smoke_failed type=%s error=%r", type(exc).__name__, exc)
        session.run.error("traceback:\n%s", traceback.format_exc())
        fail_marker = session.root / "FAIL_PHYS91_ENDPOINT_IK_SMOKE"
        fail_marker.write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
        result = 10
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
