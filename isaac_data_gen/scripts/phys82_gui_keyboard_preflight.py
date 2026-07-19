#!/usr/bin/env python3
"""GUI and official bi_keyboard preflight for PHYS-8."""

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

from phys_data_gen.logging_utils import log_environment, mark_fail, mark_pass, setup_logging
from phys_data_gen.phys8_tools import capture_multiview, save_json, scene_metrics


def _save_display_screenshot(output_path: Path) -> dict[str, object]:
    import numpy as np
    from PIL import ImageGrab

    image = ImageGrab.grab()
    image.save(output_path)
    array = np.asarray(image)
    grid = array[:: max(1, array.shape[0] // 96), :: max(1, array.shape[1] // 96)]
    stats = {
        "path": str(output_path),
        "shape": list(array.shape),
        "dtype": str(array.dtype),
        "min": int(np.min(array)),
        "max": int(np.max(array)),
        "mean": float(np.mean(array)),
        "std": float(np.std(array)),
        "unique_sample_count": int(len(np.unique(grid.reshape(-1, grid.shape[-1]), axis=0))) if array.ndim == 3 else 0,
    }
    if stats["std"] < 2.0:
        raise RuntimeError(f"display screenshot appears blank: {stats}")
    if stats["unique_sample_count"] < 10:
        raise RuntimeError(f"display screenshot has too few sampled colors: {stats}")
    return stats


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-name", default=None)
    parser.add_argument("--task", default="LeIsaac-XTrainer-PickCube-v0")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--num-envs", type=int, default=1)
    parser.add_argument("--seed", type=int, default=82)
    parser.add_argument("--warmup-steps", type=int, default=12)
    parser.add_argument("--screenshot-delay-sec", type=float, default=1.0)
    args = parser.parse_args()

    session = setup_logging(session_name=args.session_name)
    session.run.info("phys82_gui_keyboard_preflight_start task=%s seed=%d", args.task, args.seed)
    log_environment(
        session,
        extra={
            "stage": "PHYS-8.2",
            "task": args.task,
            "seed": args.seed,
            "manual_keyboard_entry": "bash scripts/phys81_keyboard_teleop.sh",
        },
    )

    from isaaclab.app import AppLauncher

    app_launcher = AppLauncher(headless=False, enable_cameras=True)
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
        zero_action = torch.zeros(env.action_space.shape, dtype=torch.float32, device=env.device)
        for step_idx in range(args.warmup_steps):
            obs, reward, terminated, truncated, info = env.step(zero_action)
            env.sim.render()
            simulation_app.update()
            session.data.info("warmup_step=%d terminated=%s truncated=%s", step_idx, terminated, truncated)

        images, camera_stats = capture_multiview(env, obs, "gui_preflight_cameras", session)
        metrics = scene_metrics(env, obs)

        time.sleep(max(0.0, args.screenshot_delay_sec))
        for _ in range(4):
            simulation_app.update()
            env.sim.render()
        screenshot_stats = _save_display_screenshot(session.root / "gui_display_screenshot.png")
        session.data.info("display_screenshot_stats=%s", json.dumps(screenshot_stats, sort_keys=True))

        report = {
            "stage": "PHYS-8.2",
            "task": args.task,
            "seed": args.seed,
            "camera_stats": camera_stats,
            "scene_metrics": metrics,
            "display_screenshot": screenshot_stats,
            "gui_mode": "headless_false_enable_cameras_true",
            "manual_keyboard_entry": "ACCEPT_NVIDIA_OMNIVERSE_EULA=YES bash scripts/phys81_keyboard_teleop.sh",
            "keyboard_controls": {
                "start": "B",
                "left_arm": "Q/W/E/A/S/D, Z+key for reverse",
                "right_arm": "U/I/O/J/K/L, Z+key for reverse",
                "grippers": "G/H, Z+key for reverse",
                "reset_failed": "R",
                "mark_success": "N",
                "quit": "Ctrl+C",
            },
        }
        save_json(session.root / "gui_keyboard_preflight_report.json", report)
        session.run.info("gui_keyboard_preflight_report_saved path=%s", session.root / "gui_keyboard_preflight_report.json")

        mark_pass(session, "PASS_PHYS82_GUI_KEYBOARD_PREFLIGHT", "GUI and keyboard preflight passed")
        session.run.info("phys82_gui_keyboard_preflight_ok")
        result = 0
    except BaseException as exc:
        session.run.error("phys82_gui_keyboard_preflight_failed type=%s error=%r", type(exc).__name__, exc)
        session.run.error("traceback:\n%s", traceback.format_exc())
        mark_fail(session, "FAIL_PHYS82_GUI_KEYBOARD_PREFLIGHT", f"{type(exc).__name__}: {exc}")
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
