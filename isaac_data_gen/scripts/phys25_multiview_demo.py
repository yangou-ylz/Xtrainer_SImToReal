#!/usr/bin/env python3
"""Finite-step multi-view render and deterministic action demo for X-Trainer PickCube."""

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

from phys_data_gen.action_mapping import command14_to_leisaac16, make_replay_command14
from phys_data_gen.logging_utils import log_environment, mark_pass, setup_logging


CAMERAS = ("top", "left_wrist", "right_wrist")


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


def _save_multiview_grid(images: dict[str, object], output_path: Path) -> None:
    from PIL import Image, ImageDraw
    import numpy as np

    tiles = []
    label_h = 28
    for name in CAMERAS:
        image = Image.fromarray(images[name])
        canvas = Image.new("RGB", (image.width, image.height + label_h), "white")
        canvas.paste(image, (0, label_h))
        draw = ImageDraw.Draw(canvas)
        draw.text((10, 7), name, fill=(0, 0, 0))
        tiles.append(np.asarray(canvas))
    separator = np.full((tiles[0].shape[0], 8, 3), 255, dtype=np.uint8)
    grid = np.concatenate([tiles[0], separator, tiles[1], separator, tiles[2]], axis=1)
    Image.fromarray(grid).save(output_path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-name", default=None)
    parser.add_argument("--steps", type=int, default=10)
    parser.add_argument("--task", default="LeIsaac-XTrainer-PickCube-v0")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--num-envs", type=int, default=1)
    args = parser.parse_args()

    session = setup_logging(session_name=args.session_name)
    session.run.info("phys25_multiview_demo_start task=%s steps=%d", args.task, args.steps)
    log_environment(session, extra={"stage": "PHYS-2.5", "task": args.task, "steps": args.steps})

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
        env_cfg.seed = 25
        if hasattr(env_cfg, "terminations") and hasattr(env_cfg.terminations, "time_out"):
            env_cfg.terminations.time_out = None

        for camera_name in ("stereo_left", "stereo_right"):
            if hasattr(env_cfg.scene, camera_name):
                setattr(env_cfg.scene, camera_name, None)
                session.run.info("disabled_scene_camera=%s", camera_name)

        session.run.info("gym_make_start")
        env = gym.make(args.task, cfg=env_cfg).unwrapped
        session.run.info("gym_make_ok action_space=%s observation_space=%s", env.action_space, env.observation_space)

        obs, info = env.reset()
        session.data.info("reset_ok obs_type=%s info_keys=%s", type(obs).__name__, sorted(info.keys()) if isinstance(info, dict) else type(info).__name__)

        action_shape = env.action_space.shape
        if action_shape is None:
            session.run.error("action_space_shape_missing action_space=%s", env.action_space)
            return 4
        replay16 = command14_to_leisaac16(make_replay_command14(left_gripper=0.25, right_gripper=0.25))
        if len(action_shape) != 2 or action_shape[-1] != replay16.shape[-1]:
            raise RuntimeError(f"unexpected action_space shape {action_shape}; expected (*, {replay16.shape[-1]})")
        action = torch.as_tensor(replay16, dtype=torch.float32, device=env.device).reshape(1, -1).repeat(action_shape[0], 1)
        session.data.info("replay_action_shape=%s action_max_abs=%.6f", tuple(action.shape), action.abs().max().detach().item())

        for step_idx in range(args.steps):
            obs, reward, terminated, truncated, info = env.step(action)
            env.sim.render()
            session.data.info("step=%d terminated=%s truncated=%s", step_idx, terminated, truncated)

        images = {}
        stats = {}
        for camera_name in CAMERAS:
            obs_image = _extract_obs_image(obs, camera_name)
            if obs_image is not None:
                image = _to_numpy_image(obs_image)
                source = f"observation.policy.{camera_name}"
            else:
                sensor = env.scene.sensors[camera_name]
                image = _to_numpy_image(sensor.data.output["rgb"])
                source = f"scene.sensors.{camera_name}.data.output.rgb"
            camera_stats = _image_stats(image)
            camera_stats["source"] = source
            camera_stats["camera"] = camera_name
            stats[camera_name] = camera_stats
            images[camera_name] = image
            iio.imwrite(session.root / f"{camera_name}.png", image)
            session.data.info("camera=%s stats=%s", camera_name, json.dumps(camera_stats, sort_keys=True))

            if image.shape != (480, 640, 3):
                raise RuntimeError(f"{camera_name}: unexpected image shape: {image.shape}")
            if camera_stats["std"] < 2.0:
                raise RuntimeError(f"{camera_name}: image appears blank: std={camera_stats['std']}")
            if camera_stats["unique_sample_count"] < 10:
                raise RuntimeError(f"{camera_name}: too few sampled colors: {camera_stats['unique_sample_count']}")

        grid_path = session.root / "multiview_grid.png"
        stats_path = session.root / "multiview_stats.json"
        _save_multiview_grid(images, grid_path)
        stats_path.write_text(json.dumps(stats, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        session.run.info("multiview_grid_saved path=%s", grid_path)
        session.run.info("multiview_stats_saved path=%s", stats_path)

        policy = obs.get("policy", {}) if isinstance(obs, dict) else {}
        action_obs = policy.get("actions")
        if action_obs is not None:
            action_obs_max = float(action_obs.detach().abs().max().item()) if hasattr(action_obs, "detach") else 0.0
            session.data.info("observation_actions_max_abs=%.6f", action_obs_max)
            if action_obs_max <= 0.0:
                raise RuntimeError("action observation did not reflect deterministic replay action")

        mark_pass(session, "PASS_PHYS25_MULTIVIEW_DEMO", "multi-view finite-step demo passed")
        session.run.info("phys25_multiview_demo_ok")
        result = 0
    except BaseException as exc:
        session.run.error("phys25_multiview_demo_failed type=%s error=%r", type(exc).__name__, exc)
        session.run.error("traceback:\n%s", traceback.format_exc())
        fail_marker = session.root / "FAIL_PHYS25_MULTIVIEW_DEMO"
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
