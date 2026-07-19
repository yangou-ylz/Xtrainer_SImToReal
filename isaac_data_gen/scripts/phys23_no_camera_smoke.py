#!/usr/bin/env python3
"""Finite-step no-camera smoke test for LeIsaac X-Trainer PickCube."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import traceback


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from phys_data_gen.logging_utils import log_environment, mark_pass, setup_logging


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-name", default=None)
    parser.add_argument("--steps", type=int, default=5)
    parser.add_argument("--task", default="LeIsaac-XTrainer-PickCube-v0")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--num-envs", type=int, default=1)
    args = parser.parse_args()

    session = setup_logging(session_name=args.session_name)
    session.run.info("phys23_no_camera_smoke_start task=%s steps=%d", args.task, args.steps)
    log_environment(session, extra={"stage": "PHYS-2.3", "task": args.task, "steps": args.steps})

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
        env_cfg.seed = 23
        if hasattr(env_cfg, "terminations") and hasattr(env_cfg.terminations, "time_out"):
            env_cfg.terminations.time_out = None

        # The upstream task always declares tiled cameras. For the low-load
        # smoke gate we remove them from the runtime cfg instead of editing
        # upstream source.
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
            if hasattr(reward, "detach"):
                reward_value = reward.detach().mean().item()
            else:
                reward_value = float(reward)
            session.data.info(
                "step=%d reward_mean=%.6f terminated=%s truncated=%s",
                step_idx,
                reward_value,
                terminated,
                truncated,
            )

        mark_pass(session, "PASS_PHYS23_NO_CAMERA_SMOKE", "no-camera finite-step smoke passed")
        session.run.info("phys23_no_camera_smoke_ok")
        result = 0
    except BaseException as exc:
        session.run.error("phys23_no_camera_smoke_failed type=%s error=%r", type(exc).__name__, exc)
        session.run.error("traceback:\n%s", traceback.format_exc())
        fail_marker = session.root / "FAIL_PHYS23_NO_CAMERA_SMOKE"
        fail_marker.write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
        result = 10
    finally:
        if env is not None:
            try:
                env.close()
            except Exception as exc:
                session.run.warning("env_close_warning=%r", exc)
        if result == 0:
            try:
                simulation_app.close(wait_for_replicator=False, skip_cleanup=True)
            except TypeError:
                simulation_app.close()
        else:
            session.run.error("skip_simulation_app_close_after_failure_to_preserve_traceback")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
