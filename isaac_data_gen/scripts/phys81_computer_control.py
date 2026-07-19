#!/usr/bin/env python3
"""Validate computer-command control of X-Trainer joints and grippers in LeIsaac."""

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
from phys_data_gen.image_validation import (
    CAMERAS,
    extract_obs_image,
    image_stats,
    mean_abs_diff,
    save_multiview_grid,
    to_numpy_image,
)
from phys_data_gen.logging_utils import log_environment, mark_pass, setup_logging


def _tensor_to_numpy(value):
    import numpy as np

    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    else:
        value = np.asarray(value)
    return value


def _policy_array(obs: dict, key: str):
    policy = obs.get("policy", {}) if isinstance(obs, dict) else {}
    if key not in policy:
        raise KeyError(f"missing policy observation key: {key}")
    array = _tensor_to_numpy(policy[key])
    if array.ndim >= 2 and array.shape[0] == 1:
        array = array[0]
    return array


def _capture_multiview(env, obs: dict, output_prefix: str, session) -> tuple[dict[str, object], dict[str, object]]:
    import imageio.v3 as iio

    images = {}
    stats = {}
    for camera_name in CAMERAS:
        obs_image = extract_obs_image(obs, camera_name)
        if obs_image is not None:
            image = to_numpy_image(obs_image)
            source = f"observation.policy.{camera_name}"
        else:
            sensor = env.scene.sensors[camera_name]
            image = to_numpy_image(sensor.data.output["rgb"])
            source = f"scene.sensors.{camera_name}.data.output.rgb"
        camera_stats = image_stats(image)
        camera_stats["source"] = source
        camera_stats["camera"] = camera_name
        if camera_stats["shape"] != [480, 640, 3]:
            raise RuntimeError(f"{camera_name}: unexpected image shape: {camera_stats['shape']}")
        if float(camera_stats["std"]) < 2.0:
            raise RuntimeError(f"{camera_name}: image appears blank: std={camera_stats['std']}")
        if int(camera_stats["unique_sample_count"]) < 10:
            raise RuntimeError(f"{camera_name}: too few sampled colors: {camera_stats['unique_sample_count']}")
        images[camera_name] = image
        stats[camera_name] = camera_stats
        iio.imwrite(session.root / f"{output_prefix}_{camera_name}.png", image)
        session.data.info("capture=%s camera=%s stats=%s", output_prefix, camera_name, json.dumps(camera_stats, sort_keys=True))
    save_multiview_grid(images, session.root / f"{output_prefix}_grid.png", title=output_prefix)
    return images, stats


def _make_command14(name: str):
    import numpy as np

    command = np.zeros((14,), dtype=np.float32)
    if name == "home_open":
        command[6] = 0.0
        command[13] = 0.0
    elif name == "move_ready":
        command[0] = 0.16
        command[1] = -0.12
        command[3] = 0.08
        command[5] = 0.08
        command[6] = 0.10
        command[7] = -0.16
        command[8] = -0.12
        command[10] = 0.08
        command[12] = -0.08
        command[13] = 0.10
    elif name == "close_grippers":
        command = _make_command14("move_ready")
        command[6] = 1.0
        command[13] = 1.0
    elif name == "lift_after_close":
        command = _make_command14("close_grippers")
        command[1] = -0.18
        command[8] = -0.18
        command[3] = 0.12
        command[10] = 0.12
    else:
        raise ValueError(f"unknown command stage: {name}")
    return command


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-name", default=None)
    parser.add_argument("--task", default="LeIsaac-XTrainer-PickCube-v0")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--num-envs", type=int, default=1)
    parser.add_argument("--seed", type=int, default=81)
    args = parser.parse_args()

    session = setup_logging(session_name=args.session_name)
    session.run.info("phys81_computer_control_start task=%s seed=%d", args.task, args.seed)
    log_environment(session, extra={"stage": "PHYS-8.1", "task": args.task, "seed": args.seed})

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
        session.data.info("reset_ok info_keys=%s", sorted(info.keys()) if isinstance(info, dict) else type(info).__name__)

        action_shape = env.action_space.shape
        if len(action_shape) != 2 or action_shape[-1] != 16:
            raise RuntimeError(f"unexpected action_space shape {action_shape}; expected (*, 16)")

        before_images, before_stats = _capture_multiview(env, obs, "before_control", session)
        before_left_target = _policy_array(obs, "left_joint_pos_target").copy()
        before_right_target = _policy_array(obs, "right_joint_pos_target").copy()
        before_left_pos = _policy_array(obs, "left_joint_pos_rel").copy()
        before_right_pos = _policy_array(obs, "right_joint_pos_rel").copy()

        stages = [
            ("home_open", 8),
            ("move_ready", 24),
            ("close_grippers", 18),
            ("lift_after_close", 12),
        ]
        sent_actions = []
        last_action16 = None
        for stage_name, duration in stages:
            command14 = _make_command14(stage_name)
            action16 = command14_to_leisaac16(command14)
            symmetry = check_leisaac16_gripper_symmetry(action16)
            if not symmetry.passed:
                raise RuntimeError(f"{stage_name}: gripper symmetry failed: {symmetry}")
            action = torch.as_tensor(action16, dtype=torch.float32, device=env.device).reshape(1, -1).repeat(action_shape[0], 1)
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
            sent_actions.append(
                {
                    "stage": stage_name,
                    "duration": duration,
                    "command14": command14.tolist(),
                    "leisaac16": action16.tolist(),
                    "gripper_symmetry": {
                        "left_max_abs": symmetry.left_max_abs,
                        "right_max_abs": symmetry.right_max_abs,
                        "tolerance": symmetry.tolerance,
                        "passed": symmetry.passed,
                    },
                }
            )
            last_action16 = action16

        after_images, after_stats = _capture_multiview(env, obs, "after_control", session)
        after_left_target = _policy_array(obs, "left_joint_pos_target").copy()
        after_right_target = _policy_array(obs, "right_joint_pos_target").copy()
        after_left_pos = _policy_array(obs, "left_joint_pos_rel").copy()
        after_right_pos = _policy_array(obs, "right_joint_pos_rel").copy()
        observed_action = _policy_array(obs, "actions").copy()

        if last_action16 is None:
            raise RuntimeError("no actions were sent")
        action_error = float(np.max(np.abs(observed_action - last_action16)))
        if action_error > 1e-5:
            raise RuntimeError(f"observation action mismatch: max_abs_error={action_error}")

        target_delta = {
            "left": float(np.max(np.abs(after_left_target - before_left_target))),
            "right": float(np.max(np.abs(after_right_target - before_right_target))),
        }
        pos_delta = {
            "left": float(np.max(np.abs(after_left_pos - before_left_pos))),
            "right": float(np.max(np.abs(after_right_pos - before_right_pos))),
        }
        gripper_target = {
            "left_j7_plus_j8": float(after_left_target[6] + after_left_target[7]),
            "right_j7_plus_j8": float(after_right_target[6] + after_right_target[7]),
            "left_width_joint_j8": float(after_left_target[7]),
            "right_width_joint_j8": float(after_right_target[7]),
        }
        if max(target_delta.values()) < 0.02:
            raise RuntimeError(f"joint target delta too small: {target_delta}")
        if max(pos_delta.values()) < 0.002:
            raise RuntimeError(f"joint position delta too small: {pos_delta}")
        if abs(gripper_target["left_j7_plus_j8"]) > 1e-4 or abs(gripper_target["right_j7_plus_j8"]) > 1e-4:
            raise RuntimeError(f"gripper target symmetry failed: {gripper_target}")
        if gripper_target["left_width_joint_j8"] < 0.02 or gripper_target["right_width_joint_j8"] < 0.02:
            raise RuntimeError(f"gripper target did not close enough: {gripper_target}")

        image_diffs = {camera_name: mean_abs_diff(before_images[camera_name], after_images[camera_name]) for camera_name in CAMERAS}
        if max(image_diffs.values()) < 0.5:
            raise RuntimeError(f"before/after image diff too small: {image_diffs}")

        report = {
            "stage": "PHYS-8.1",
            "task": args.task,
            "seed": args.seed,
            "sent_actions": sent_actions,
            "observed_action_max_abs_error": action_error,
            "target_delta_max_abs": target_delta,
            "position_delta_max_abs": pos_delta,
            "gripper_target": gripper_target,
            "image_diffs_before_after": image_diffs,
            "before_stats": before_stats,
            "after_stats": after_stats,
            "manual_keyboard_entry": "bash scripts/phys81_keyboard_teleop.sh",
        }
        report_path = session.root / "computer_control_report.json"
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        session.run.info("computer_control_report_saved path=%s", report_path)
        session.data.info("computer_control_report=%s", json.dumps(report, sort_keys=True))

        mark_pass(session, "PASS_PHYS81_COMPUTER_CONTROL", "computer command control validation passed")
        session.run.info("phys81_computer_control_ok")
        result = 0
    except BaseException as exc:
        session.run.error("phys81_computer_control_failed type=%s error=%r", type(exc).__name__, exc)
        session.run.error("traceback:\n%s", traceback.format_exc())
        fail_marker = session.root / "FAIL_PHYS81_COMPUTER_CONTROL"
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
