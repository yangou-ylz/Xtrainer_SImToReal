#!/usr/bin/env python3
"""Convert validated X-Trainer LeIsaac HDF5 data to a local LeRobot dataset."""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
import traceback
from pathlib import Path

import h5py
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
UPSTREAM_CONVERTER = ROOT / "external/x-trainer/scripts/convert/isaaclab2lerobot_xtrainer.py"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lerobot.datasets.lerobot_dataset import LeRobotDataset

from phys_data_gen.dataset_validation import validate_hdf5_dataset
from phys_data_gen.logging_utils import log_environment, mark_fail, mark_pass, setup_logging


def load_upstream_features() -> dict:
    spec = importlib.util.spec_from_file_location("xtrainer_lerobot_converter", UPSTREAM_CONVERTER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load upstream converter: {UPSTREAM_CONVERTER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.XTRAINER_FEATURES


def preprocess_joint_pos(joint_pos: np.ndarray) -> np.ndarray:
    return joint_pos.astype(np.float32)


def jsonable_shape(value) -> list[int]:
    return [int(v) for v in value]


def convert_demo(
    dataset: LeRobotDataset,
    demo_group: h5py.Group,
    demo_name: str,
    *,
    task: str,
    skip_first_frames: int,
    logger,
) -> dict:
    actions = preprocess_joint_pos(np.asarray(demo_group["actions"]))
    left_joint_pos = preprocess_joint_pos(np.asarray(demo_group["obs/left_joint_pos_rel"]))
    right_joint_pos = preprocess_joint_pos(np.asarray(demo_group["obs/right_joint_pos_rel"]))
    joint_pos = np.concatenate([left_joint_pos, right_joint_pos], axis=1)
    top_images = np.asarray(demo_group["obs/top"])
    left_images = np.asarray(demo_group["obs/left_wrist"])
    right_images = np.asarray(demo_group["obs/right_wrist"])

    frame_count = actions.shape[0]
    if frame_count <= skip_first_frames:
        raise ValueError(f"{demo_name} has {frame_count} frames, cannot skip first {skip_first_frames}")
    if not (
        frame_count
        == joint_pos.shape[0]
        == top_images.shape[0]
        == left_images.shape[0]
        == right_images.shape[0]
    ):
        raise ValueError(f"{demo_name} frame counts are inconsistent")

    added = 0
    for frame_index in range(skip_first_frames, frame_count):
        frame = {
            "action": actions[frame_index],
            "observation.state": joint_pos[frame_index],
            "observation.images.top": top_images[frame_index],
            "observation.images.left_wrist": left_images[frame_index],
            "observation.images.right_wrist": right_images[frame_index],
        }
        dataset.add_frame(frame=frame, task=task)
        added += 1

    dataset.save_episode()
    logger.info(
        "converted_demo demo=%s source_frames=%s skipped=%s lerobot_frames=%s",
        demo_name,
        frame_count,
        skip_first_frames,
        added,
    )
    return {
        "demo": demo_name,
        "source_frames": int(frame_count),
        "skipped_frames": int(skip_first_frames),
        "lerobot_frames": int(added),
    }


def inspect_lerobot_dataset(root: Path, repo_id: str, video_backend: str | None) -> dict:
    dataset = LeRobotDataset(repo_id=repo_id, root=root, video_backend=video_backend)
    sample = dataset[0]
    sample_summary = {}
    for key in [
        "action",
        "observation.state",
        "observation.images.top",
        "observation.images.left_wrist",
        "observation.images.right_wrist",
    ]:
        value = sample[key]
        shape = tuple(value.shape) if hasattr(value, "shape") else ()
        dtype = str(value.dtype) if hasattr(value, "dtype") else type(value).__name__
        sample_summary[key] = {"shape": jsonable_shape(shape), "dtype": dtype}

    return {
        "repo_id": dataset.repo_id,
        "root": str(dataset.root),
        "num_episodes": int(dataset.num_episodes),
        "num_frames": int(len(dataset)),
        "fps": int(dataset.fps),
        "features": sorted(dataset.features.keys()),
        "sample": sample_summary,
        "task": sample.get("task", ""),
    }


def write_report(path: Path, report: dict) -> None:
    lines = [
        "# PHYS-4 LeRobot Conversion Report",
        "",
        f"- Status: `{report['status']}`",
        f"- Input HDF5: `{report['input_hdf5']}`",
        f"- Output root: `{report['output_root']}`",
        f"- Repo ID: `{report['repo_id']}`",
        f"- Episodes: `{report['inspection']['num_episodes']}`",
        f"- Frames: `{report['inspection']['num_frames']}`",
        f"- FPS: `{report['inspection']['fps']}`",
        "",
        "## Converted Demos",
        "",
        "| Demo | Source Frames | Skipped | LeRobot Frames |",
        "|---|---:|---:|---:|",
    ]
    for demo in report["converted_demos"]:
        lines.append(
            f"| `{demo['demo']}` | `{demo['source_frames']}` | "
            f"`{demo['skipped_frames']}` | `{demo['lerobot_frames']}` |"
        )

    lines.extend(["", "## Sample", "", "| Key | Shape | Dtype |", "|---|---:|---|"])
    for key, meta in report["inspection"]["sample"].items():
        lines.append(f"| `{key}` | `{meta['shape']}` | `{meta['dtype']}` |")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-hdf5", default="datasets/raw_hdf5/pickcube_smoke_phys30.hdf5")
    parser.add_argument("--output-root", default="datasets/lerobot/phys40_xtrainer_pickcube_smoke")
    parser.add_argument("--repo-id", default="local/xtrainer_pickcube_smoke")
    parser.add_argument("--task", default="Grab cube and place into plate")
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--robot-type", default="xtrainer_follower")
    parser.add_argument("--session-name", default=None)
    parser.add_argument("--skip-first-frames", type=int, default=5)
    parser.add_argument("--allow-smoke-unsuccessful", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--video-backend", default="pyav")
    args = parser.parse_args()

    session = setup_logging(session_name=args.session_name)
    input_hdf5 = Path(args.input_hdf5)
    if not input_hdf5.is_absolute():
        input_hdf5 = ROOT / input_hdf5
    output_root = Path(args.output_root)
    if not output_root.is_absolute():
        output_root = ROOT / output_root

    session.run.info("phys40_convert_start input=%s output=%s repo_id=%s", input_hdf5, output_root, args.repo_id)
    log_environment(
        session,
        extra={
            "stage": "PHYS-4",
            "input_hdf5": str(input_hdf5),
            "output_root": str(output_root),
            "repo_id": args.repo_id,
            "python_no_user_site": sys.flags.no_user_site,
        },
    )

    try:
        validation = validate_hdf5_dataset(input_hdf5, require_success=not args.allow_smoke_unsuccessful)
        if not validation.passed:
            raise RuntimeError(f"HDF5 validation failed before conversion: {validation.to_dict()}")
        session.data.info("pre_conversion_hdf5_validation=%s", json.dumps(validation.to_dict(), sort_keys=True))

        if output_root.exists():
            if not args.overwrite:
                raise FileExistsError(f"output root exists: {output_root}; pass --overwrite to replace it")
            shutil.rmtree(output_root)
        output_root.parent.mkdir(parents=True, exist_ok=True)

        features = load_upstream_features()
        dataset = LeRobotDataset.create(
            repo_id=args.repo_id,
            fps=args.fps,
            robot_type=args.robot_type,
            features=features,
            root=output_root,
            use_videos=True,
            video_backend=args.video_backend,
        )

        converted_demos = []
        with h5py.File(input_hdf5, "r") as h5:
            demo_names = sorted(k for k in h5["data"].keys() if k.startswith("demo_"))
            for demo_name in demo_names:
                demo_group = h5["data"][demo_name]
                success_attr = demo_group.attrs.get("success", None)
                if success_attr is False or success_attr == 0:
                    session.run.warning("skip_failed_demo demo=%s success=%s", demo_name, success_attr)
                    continue
                if success_attr is None and not args.allow_smoke_unsuccessful:
                    raise RuntimeError(f"{demo_name} missing success attr; use --allow-smoke-unsuccessful only for smoke")
                if success_attr is None:
                    session.run.warning("smoke_demo_without_success_attr demo=%s", demo_name)
                converted_demos.append(
                    convert_demo(
                        dataset,
                        demo_group,
                        demo_name,
                        task=args.task,
                        skip_first_frames=args.skip_first_frames,
                        logger=session.data,
                    )
                )

        if not converted_demos:
            raise RuntimeError("no demos converted")

        inspection = inspect_lerobot_dataset(output_root, args.repo_id, args.video_backend)
        expected_frames = sum(demo["lerobot_frames"] for demo in converted_demos)
        if inspection["num_episodes"] != len(converted_demos):
            raise RuntimeError(f"episode count mismatch: {inspection['num_episodes']} != {len(converted_demos)}")
        if inspection["num_frames"] != expected_frames:
            raise RuntimeError(f"frame count mismatch: {inspection['num_frames']} != {expected_frames}")

        report = {
            "status": "PASS",
            "input_hdf5": str(input_hdf5),
            "output_root": str(output_root),
            "repo_id": args.repo_id,
            "converted_demos": converted_demos,
            "inspection": inspection,
        }
        (session.root / "lerobot_conversion_report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        write_report(session.root / "lerobot_conversion_report.md", report)
        session.data.info("lerobot_inspection=%s", json.dumps(inspection, sort_keys=True))
        mark_pass(session, "PASS_PHYS40_LEROBOT_CONVERSION", "LeRobot conversion passed")
        session.run.info("phys40_convert_ok")
        return 0
    except BaseException as exc:
        session.run.error("phys40_convert_exception type=%s error=%r", type(exc).__name__, exc)
        session.run.error("traceback:\n%s", traceback.format_exc())
        mark_fail(session, "FAIL_PHYS40_LEROBOT_CONVERSION", f"{type(exc).__name__}: {exc}")
        return 20


if __name__ == "__main__":
    raise SystemExit(main())
