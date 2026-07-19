#!/usr/bin/env python3
"""Record a minimal deterministic HDF5 episode for LeIsaac X-Trainer PickCube."""

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


def _hdf5_tree(path: Path) -> dict[str, object]:
    import h5py

    tree: dict[str, object] = {"file": str(path), "datasets": {}, "attrs": {}}
    with h5py.File(path, "r") as h5:
        tree["attrs"] = {k: _jsonable(v) for k, v in h5.attrs.items()}

        def visit(name, obj):
            if isinstance(obj, h5py.Dataset):
                tree["datasets"][name] = {
                    "shape": list(obj.shape),
                    "dtype": str(obj.dtype),
                }
            elif isinstance(obj, h5py.Group):
                attrs = {k: _jsonable(v) for k, v in obj.attrs.items()}
                if attrs:
                    tree.setdefault("groups", {})[name] = {"attrs": attrs}

        h5.visititems(visit)
    return tree


def _jsonable(value):
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _validate_minimal_hdf5(path: Path) -> dict[str, object]:
    import h5py

    result: dict[str, object] = {"path": str(path), "checks": {}}
    with h5py.File(path, "r") as h5:
        if "data" not in h5:
            raise RuntimeError("missing /data group")
        data = h5["data"]
        demos = sorted(k for k in data.keys() if k.startswith("demo_"))
        result["demos"] = demos
        if not demos:
            raise RuntimeError("no demo_* groups found")
        demo = data[demos[0]]
        result["demo_attrs"] = {k: _jsonable(v) for k, v in demo.attrs.items()}
        num_samples = int(demo.attrs.get("num_samples", 0))
        if num_samples <= 0:
            raise RuntimeError(f"invalid num_samples={num_samples}")
        result["num_samples"] = num_samples

        required = [
            "actions",
            "obs/left_joint_pos_rel",
            "obs/right_joint_pos_rel",
            "obs/top",
            "obs/left_wrist",
            "obs/right_wrist",
        ]
        for key in required:
            if key not in demo:
                raise RuntimeError(f"missing demo dataset: {key}")
            dataset = demo[key]
            result["checks"][key] = {"shape": list(dataset.shape), "dtype": str(dataset.dtype)}
            if dataset.shape[0] != num_samples:
                raise RuntimeError(f"{key}: first dimension {dataset.shape[0]} != num_samples {num_samples}")

        if demo["actions"].shape[1:] != (16,):
            raise RuntimeError(f"actions shape mismatch: {demo['actions'].shape}")
        for image_key in ("obs/top", "obs/left_wrist", "obs/right_wrist"):
            if demo[image_key].shape[1:] != (480, 640, 3):
                raise RuntimeError(f"{image_key} shape mismatch: {demo[image_key].shape}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-name", default=None)
    parser.add_argument("--steps", type=int, default=16)
    parser.add_argument("--task", default="LeIsaac-XTrainer-PickCube-v0")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--num-envs", type=int, default=1)
    parser.add_argument("--seed", type=int, default=30)
    parser.add_argument("--dataset-file", default="datasets/raw_hdf5/pickcube_smoke_phys30.hdf5")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    session = setup_logging(session_name=args.session_name)
    dataset_path = (ROOT / args.dataset_file).resolve() if not Path(args.dataset_file).is_absolute() else Path(args.dataset_file)
    session.run.info("phys30_record_hdf5_start task=%s steps=%d dataset=%s", args.task, args.steps, dataset_path)
    log_environment(
        session,
        extra={"stage": "PHYS-3", "task": args.task, "steps": args.steps, "seed": args.seed, "dataset_file": str(dataset_path)},
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
        env.recorder_manager.flush_steps = max(args.steps + 1, 100)
        env.recorder_manager.compression = "lzf"

        obs, info = env.reset()
        session.data.info("reset_ok obs_type=%s info_keys=%s", type(obs).__name__, sorted(info.keys()) if isinstance(info, dict) else type(info).__name__)

        action_shape = env.action_space.shape
        replay16 = command14_to_leisaac16(make_replay_command14(left_gripper=0.25, right_gripper=0.25))
        if len(action_shape) != 2 or action_shape[-1] != replay16.shape[-1]:
            raise RuntimeError(f"unexpected action_space shape {action_shape}; expected (*, {replay16.shape[-1]})")
        action = torch.as_tensor(replay16, dtype=torch.float32, device=env.device).reshape(1, -1).repeat(action_shape[0], 1)
        session.data.info("record_action_shape=%s action_max_abs=%.6f", tuple(action.shape), action.abs().max().detach().item())

        for step_idx in range(args.steps):
            obs, reward, terminated, truncated, info = env.step(action)
            env.sim.render()
            session.data.info("step=%d terminated=%s truncated=%s", step_idx, terminated, truncated)

        env.recorder_manager.export_episodes(from_step=False)
        session.run.info(
            "recorder_exported successful=%s failed=%s",
            env.recorder_manager.exported_successful_episode_count,
            getattr(env.recorder_manager, "exported_failed_episode_count", "unavailable"),
        )

        if env is not None:
            env.close()
            env = None

        validation = _validate_minimal_hdf5(dataset_path)
        validation["seed"] = args.seed
        tree = _hdf5_tree(dataset_path)
        validation_path = session.root / "hdf5_smoke_validation.json"
        tree_path = session.root / "hdf5_tree.json"
        validation_path.write_text(json.dumps(validation, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tree_path.write_text(json.dumps(tree, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        session.run.info("hdf5_validation_saved path=%s", validation_path)
        session.run.info("hdf5_tree_saved path=%s", tree_path)
        session.data.info("hdf5_validation=%s", json.dumps(validation, sort_keys=True))

        mark_pass(session, "PASS_PHYS30_HDF5_SMOKE", "minimal HDF5 recording passed")
        session.run.info("phys30_record_hdf5_ok")
        result = 0
    except BaseException as exc:
        session.run.error("phys30_record_hdf5_failed type=%s error=%r", type(exc).__name__, exc)
        session.run.error("traceback:\n%s", traceback.format_exc())
        fail_marker = session.root / "FAIL_PHYS30_HDF5_SMOKE"
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
