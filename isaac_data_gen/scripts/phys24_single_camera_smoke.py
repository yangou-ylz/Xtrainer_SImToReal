#!/usr/bin/env python3
"""Finite-step single-camera smoke test for LeIsaac X-Trainer PickCube."""

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

from phys_data_gen.logging_utils import log_environment, mark_pass, setup_logging


def _to_numpy_image(value):
    import numpy as np

    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    else:
        value = np.asarray(value)
    if value.ndim == 4:
        value = value[0]
    if value.ndim != 3:
        raise ValueError(f"expected HWC or NHWC image, got shape={value.shape}")
    if value.shape[-1] > 3:
        value = value[..., :3]
    if value.dtype != np.uint8:
        value = np.clip(value, 0, 255).astype(np.uint8)
    return value


def _extract_obs_image(obs: dict, camera_name: str):
    if not isinstance(obs, dict):
        return None
    policy = obs.get("policy")
    if isinstance(policy, dict) and camera_name in policy:
        return policy[camera_name]
    if camera_name in obs:
        return obs[camera_name]
    return None


def _image_stats(image):
    import numpy as np

    grid = image[:: max(1, image.shape[0] // 64), :: max(1, image.shape[1] // 64), :]
    return {
        "shape": list(image.shape),
        "dtype": str(image.dtype),
        "min": int(np.min(image)),
        "max": int(np.max(image)),
        "mean": float(np.mean(image)),
        "std": float(np.std(image)),
        "unique_sample_count": int(len(np.unique(grid.reshape(-1, grid.shape[-1]), axis=0))),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-name", default=None)
    parser.add_argument("--steps", type=int, default=8)
    parser.add_argument("--task", default="LeIsaac-XTrainer-PickCube-v0")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--num-envs", type=int, default=1)
    parser.add_argument("--camera", default="top", choices=["top", "left_wrist", "right_wrist"])
    args = parser.parse_args()

    session = setup_logging(session_name=args.session_name)
    session.run.info(
        "phys24_single_camera_smoke_start task=%s camera=%s steps=%d",
        args.task,
        args.camera,
        args.steps,
    )
    log_environment(
        session,
        extra={"stage": "PHYS-2.4", "task": args.task, "camera": args.camera, "steps": args.steps},
    )

    from isaaclab.app import AppLauncher

    app_launcher = AppLauncher(headless=True, enable_cameras=True)
    simulation_app = app_launcher.app
    env = None

    result = 1
    try:
        import gymnasium as gym
        import imageio.v3 as iio
        import torch
        from isaaclab_tasks.utils import parse_env_cfg
        import leisaac.tasks  # noqa: F401

        env_cfg = parse_env_cfg(args.task, device=args.device, num_envs=args.num_envs)
        env_cfg.use_teleop_device("bi_keyboard")
        env_cfg.recorders = None
        env_cfg.seed = 24
        if hasattr(env_cfg, "terminations") and hasattr(env_cfg.terminations, "time_out"):
            env_cfg.terminations.time_out = None

        for camera_name in ("top", "left_wrist", "right_wrist", "stereo_left", "stereo_right"):
            if camera_name == args.camera:
                continue
            if hasattr(env_cfg.scene, camera_name):
                setattr(env_cfg.scene, camera_name, None)
                session.run.info("disabled_scene_camera=%s", camera_name)

        policy_obs = getattr(getattr(env_cfg, "observations", None), "policy", None)
        if policy_obs is not None:
            for obs_name in ("top", "left_wrist", "right_wrist"):
                if obs_name == args.camera:
                    continue
                if hasattr(policy_obs, obs_name):
                    setattr(policy_obs, obs_name, None)
                    session.run.info("disabled_camera_observation=%s", obs_name)

        session.run.info("gym_make_start")
        env = gym.make(args.task, cfg=env_cfg).unwrapped
        session.run.info("gym_make_ok action_space=%s observation_space=%s", env.action_space, env.observation_space)

        obs, info = env.reset()
        session.data.info("reset_ok obs_type=%s info_keys=%s", type(obs).__name__, sorted(info.keys()) if isinstance(info, dict) else type(info).__name__)

        action_shape = env.action_space.shape
        if action_shape is None:
            session.run.error("action_space_shape_missing action_space=%s", env.action_space)
            return 4
        action = torch.zeros(action_shape, device=env.device)
        session.data.info("action_shape=%s action_device=%s", tuple(action.shape), action.device)

        for step_idx in range(args.steps):
            obs, reward, terminated, truncated, info = env.step(action)
            env.sim.render()
            session.data.info("step=%d terminated=%s truncated=%s", step_idx, terminated, truncated)

        obs_image = _extract_obs_image(obs, args.camera)
        if obs_image is not None:
            image = _to_numpy_image(obs_image)
            source = f"observation.policy.{args.camera}"
        else:
            sensor = env.scene.sensors[args.camera]
            image = _to_numpy_image(sensor.data.output["rgb"])
            source = f"scene.sensors.{args.camera}.data.output.rgb"

        stats = _image_stats(image)
        stats["source"] = source
        stats["camera"] = args.camera
        stats["pass_thresholds"] = {
            "height": 480,
            "width": 640,
            "channels": 3,
            "min_std": 2.0,
            "min_unique_sample_count": 10,
        }
        session.data.info("camera_image_stats=%s", json.dumps(stats, sort_keys=True))

        image_path = session.root / "camera_sample.png"
        stats_path = session.root / "camera_stats.json"
        iio.imwrite(image_path, image)
        stats_path.write_text(json.dumps(stats, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        session.run.info("camera_sample_saved path=%s", image_path)
        session.run.info("camera_stats_saved path=%s", stats_path)

        if image.shape != (480, 640, 3):
            raise RuntimeError(f"unexpected camera image shape: {image.shape}")
        if stats["std"] < 2.0:
            raise RuntimeError(f"camera image appears blank: std={stats['std']}")
        if stats["unique_sample_count"] < 10:
            raise RuntimeError(f"camera image has too few sampled colors: {stats['unique_sample_count']}")

        mark_pass(session, "PASS_PHYS24_SINGLE_CAMERA_SMOKE", "single-camera finite-step smoke passed")
        session.run.info("phys24_single_camera_smoke_ok")
        result = 0
    except BaseException as exc:
        session.run.error("phys24_single_camera_smoke_failed type=%s error=%r", type(exc).__name__, exc)
        session.run.error("traceback:\n%s", traceback.format_exc())
        fail_marker = session.root / "FAIL_PHYS24_SINGLE_CAMERA_SMOKE"
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
