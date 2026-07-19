#!/usr/bin/env python3
"""Finite realtime multi-view render validation for X-Trainer PickCube."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
import traceback


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from phys_data_gen.action_mapping import command14_to_leisaac16
from phys_data_gen.image_validation import (
    CAMERAS,
    extract_obs_image,
    image_stats,
    mean_abs_diff,
    save_multiview_grid,
    to_numpy_image,
)
from phys_data_gen.logging_utils import log_environment, mark_pass, setup_logging


def _capture_multiview(env, obs: dict) -> tuple[dict[str, object], dict[str, object]]:
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
        images[camera_name] = image
        stats[camera_name] = camera_stats
    return images, stats


def _validate_image(camera_name: str, stats: dict[str, object]) -> None:
    if stats["shape"] != [480, 640, 3]:
        raise RuntimeError(f"{camera_name}: unexpected image shape: {stats['shape']}")
    if float(stats["std"]) < 2.0:
        raise RuntimeError(f"{camera_name}: image appears blank: std={stats['std']}")
    if int(stats["unique_sample_count"]) < 10:
        raise RuntimeError(f"{camera_name}: too few sampled colors: {stats['unique_sample_count']}")


def _make_command14(progress: float):
    import numpy as np

    progress = float(max(0.0, min(1.0, progress)))
    command = np.zeros((14,), dtype=np.float32)
    command[0] = 0.22 * progress
    command[1] = -0.10 * progress
    command[5] = 0.12 * progress
    command[6] = 0.20 + 0.35 * progress
    command[7] = -0.22 * progress
    command[8] = -0.10 * progress
    command[12] = -0.12 * progress
    command[13] = 0.20 + 0.35 * progress
    return command


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-name", default=None)
    parser.add_argument("--steps", type=int, default=60)
    parser.add_argument("--step-hz", type=float, default=15.0)
    parser.add_argument("--save-every", type=int, default=15)
    parser.add_argument("--task", default="LeIsaac-XTrainer-PickCube-v0")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--num-envs", type=int, default=1)
    parser.add_argument("--seed", type=int, default=80)
    args = parser.parse_args()

    if args.steps < 3:
        raise SystemExit("--steps must be >= 3")
    if args.save_every < 1:
        raise SystemExit("--save-every must be >= 1")
    if args.step_hz <= 0.0:
        raise SystemExit("--step-hz must be > 0")

    session = setup_logging(session_name=args.session_name)
    session.run.info(
        "phys80_realtime_view_start task=%s steps=%d step_hz=%.3f save_every=%d",
        args.task,
        args.steps,
        args.step_hz,
        args.save_every,
    )
    log_environment(
        session,
        extra={"stage": "PHYS-8.0", "task": args.task, "steps": args.steps, "step_hz": args.step_hz, "seed": args.seed},
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
        session.data.info("reset_ok info_keys=%s", sorted(info.keys()) if isinstance(info, dict) else type(info).__name__)

        action_shape = env.action_space.shape
        if len(action_shape) != 2 or action_shape[-1] != 16:
            raise RuntimeError(f"unexpected action_space shape {action_shape}; expected (*, 16)")

        capture_steps = set(range(0, args.steps, args.save_every))
        capture_steps.add(args.steps - 1)
        captures: dict[int, dict[str, object]] = {}
        frame_for_gif = []

        target_dt = 1.0 / args.step_hz
        start_time = time.monotonic()
        next_tick = start_time

        for step_idx in range(args.steps):
            progress = step_idx / float(args.steps - 1)
            action16 = command14_to_leisaac16(_make_command14(progress))
            action = torch.as_tensor(action16, dtype=torch.float32, device=env.device).reshape(1, -1).repeat(action_shape[0], 1)
            obs, reward, terminated, truncated, info = env.step(action)
            env.sim.render()
            session.data.info(
                "step=%d progress=%.4f action_max_abs=%.6f terminated=%s truncated=%s",
                step_idx,
                progress,
                action.abs().max().detach().item(),
                terminated,
                truncated,
            )

            if step_idx in capture_steps:
                images, stats = _capture_multiview(env, obs)
                for camera_name, camera_stats in stats.items():
                    _validate_image(camera_name, camera_stats)
                    iio.imwrite(session.root / f"step_{step_idx:03d}_{camera_name}.png", images[camera_name])
                    session.data.info(
                        "capture_step=%d camera=%s stats=%s",
                        step_idx,
                        camera_name,
                        json.dumps(camera_stats, sort_keys=True),
                    )
                grid_path = session.root / f"step_{step_idx:03d}_grid.png"
                save_multiview_grid(images, grid_path, title=f"step {step_idx:03d}")
                frame_for_gif.append(images["top"])
                captures[step_idx] = {"stats": stats, "grid": str(grid_path)}

            next_tick += target_dt
            sleep_time = next_tick - time.monotonic()
            if sleep_time > 0:
                time.sleep(min(sleep_time, target_dt))

        elapsed = time.monotonic() - start_time
        actual_fps = args.steps / elapsed if elapsed > 0 else 0.0
        session.run.info("realtime_loop_done elapsed_sec=%.3f actual_fps=%.3f", elapsed, actual_fps)

        first_step = min(captures)
        last_step = max(captures)
        first_images = {}
        last_images = {}
        for camera_name in CAMERAS:
            first_images[camera_name] = iio.imread(session.root / f"step_{first_step:03d}_{camera_name}.png")
            last_images[camera_name] = iio.imread(session.root / f"step_{last_step:03d}_{camera_name}.png")

        frame_diffs = {camera_name: mean_abs_diff(first_images[camera_name], last_images[camera_name]) for camera_name in CAMERAS}
        max_frame_diff = max(frame_diffs.values())
        if max_frame_diff < 0.15:
            raise RuntimeError(f"multi-frame image diff too small: {frame_diffs}")

        if frame_for_gif:
            iio.imwrite(session.root / "top_realtime_preview.gif", frame_for_gif, duration=max(target_dt * args.save_every, 0.05), loop=0)

        report = {
            "stage": "PHYS-8.0",
            "task": args.task,
            "steps": args.steps,
            "requested_step_hz": args.step_hz,
            "actual_fps": actual_fps,
            "capture_steps": sorted(captures.keys()),
            "frame_diffs_first_last": frame_diffs,
            "max_frame_diff": max_frame_diff,
            "captures": captures,
        }
        report_path = session.root / "realtime_view_report.json"
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        session.run.info("realtime_view_report_saved path=%s", report_path)

        final_grid = session.root / "multiview_realtime_final.png"
        save_multiview_grid(last_images, final_grid, title="PHYS-8.0 final")
        session.run.info("final_grid_saved path=%s", final_grid)

        mark_pass(session, "PASS_PHYS80_REALTIME_VIEW", "realtime multi-view validation passed")
        session.run.info("phys80_realtime_view_ok")
        result = 0
    except BaseException as exc:
        session.run.error("phys80_realtime_view_failed type=%s error=%r", type(exc).__name__, exc)
        session.run.error("traceback:\n%s", traceback.format_exc())
        fail_marker = session.root / "FAIL_PHYS80_REALTIME_VIEW"
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
