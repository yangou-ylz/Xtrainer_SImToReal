#!/usr/bin/env python3
"""Export X-Trainer HDF5 episodes to MP4 previews and joint trajectories."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys
import traceback
from typing import Any

import cv2
import h5py
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from phys_data_gen.image_validation import CAMERAS, image_stats, mean_abs_diff, save_multiview_grid
from phys_data_gen.logging_utils import log_environment, mark_fail, mark_pass, setup_logging


JOINT_NAMES = [
    "J1_1",
    "J1_2",
    "J1_3",
    "J1_4",
    "J1_5",
    "J1_6",
    "J1_7",
    "J1_8",
    "J2_1",
    "J2_2",
    "J2_3",
    "J2_4",
    "J2_5",
    "J2_6",
    "J2_7",
    "J2_8",
]


def _jsonable(value: Any) -> Any:
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, np.ndarray):
        return value.tolist()
    return value


def _read_demo(dataset_file: Path, demo_name: str) -> dict[str, Any]:
    if not dataset_file.exists():
        raise FileNotFoundError(f"dataset does not exist: {dataset_file}")

    with h5py.File(dataset_file, "r") as h5:
        demo_path = f"data/{demo_name}"
        if demo_path not in h5:
            available = sorted(h5.get("data", {}).keys()) if "data" in h5 else []
            raise KeyError(f"missing {demo_path}; available demos={available}")

        demo = h5[demo_path]
        images = {camera: np.asarray(demo[f"obs/{camera}"]) for camera in CAMERAS}
        left_state = np.asarray(demo["obs/left_joint_pos_rel"], dtype=np.float32)
        right_state = np.asarray(demo["obs/right_joint_pos_rel"], dtype=np.float32)
        return {
            "attrs": {key: _jsonable(value) for key, value in demo.attrs.items()},
            "actions": np.asarray(demo["actions"], dtype=np.float32),
            "state": np.concatenate([left_state, right_state], axis=1),
            "images": images,
        }


def _ensure_rgb_uint8(frames: np.ndarray, camera_name: str) -> np.ndarray:
    if frames.ndim != 4 or frames.shape[-1] != 3:
        raise ValueError(f"{camera_name} must be [T,H,W,3], got shape={frames.shape}")
    if frames.dtype != np.uint8:
        frames = np.clip(frames, 0, 255).astype(np.uint8)
    return frames


def _write_mp4(path: Path, frames_rgb: np.ndarray, fps: float) -> dict[str, Any]:
    frames_rgb = _ensure_rgb_uint8(frames_rgb, path.stem)
    height, width = frames_rgb.shape[1:3]
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    if not writer.isOpened():
        raise RuntimeError(f"failed to open VideoWriter for {path}")
    for frame in frames_rgb:
        writer.write(cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
    writer.release()

    capture = cv2.VideoCapture(str(path))
    readable = capture.isOpened()
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT)) if readable else 0
    read_ok, _ = capture.read() if readable else (False, None)
    capture.release()
    return {
        "path": str(path),
        "bytes": path.stat().st_size if path.exists() else 0,
        "readable": bool(readable),
        "first_frame_readable": bool(read_ok),
        "frame_count": frame_count,
        "expected_frames": int(frames_rgb.shape[0]),
        "width": int(width),
        "height": int(height),
        "fps": float(fps),
    }


def _make_multiview_frames(images: dict[str, np.ndarray]) -> np.ndarray:
    frames = [_ensure_rgb_uint8(images[camera], camera) for camera in CAMERAS]
    frame_count = frames[0].shape[0]
    output = []
    for index in range(frame_count):
        tiles = []
        for camera, camera_frames in zip(CAMERAS, frames):
            tile = camera_frames[index].copy()
            label = f"{camera} frame={index}"
            cv2.rectangle(tile, (0, 0), (tile.shape[1], 28), (255, 255, 255), thickness=-1)
            cv2.putText(tile, label, (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 1, cv2.LINE_AA)
            tiles.append(tile)
        output.append(np.concatenate(tiles, axis=1))
    return np.stack(output, axis=0)


def _write_csv(path: Path, times: np.ndarray, values: np.ndarray, names: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["frame", "time_sec", *names])
        for frame_index, row in enumerate(values):
            writer.writerow([frame_index, f"{times[frame_index]:.9f}", *[f"{float(v):.9f}" for v in row]])


def _validate_shapes(actions: np.ndarray, state: np.ndarray, images: dict[str, np.ndarray]) -> list[str]:
    issues: list[str] = []
    if actions.ndim != 2 or actions.shape[1] != 16:
        issues.append(f"actions shape must be [T,16], got {actions.shape}")
    if state.ndim != 2 or state.shape[1] != 16:
        issues.append(f"state shape must be [T,16], got {state.shape}")
    lengths = {"actions": actions.shape[0], "state": state.shape[0]}
    for camera, frames in images.items():
        lengths[camera] = frames.shape[0]
        if frames.ndim != 4 or frames.shape[1:] != (480, 640, 3):
            issues.append(f"{camera} shape must be [T,480,640,3], got {frames.shape}")
    if len(set(lengths.values())) != 1:
        issues.append(f"frame counts do not match: {lengths}")
    if not np.all(np.isfinite(actions)):
        issues.append("actions contain NaN or Inf")
    if not np.all(np.isfinite(state)):
        issues.append("state contains NaN or Inf")
    return issues


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# PHYS-9.0 HDF5 Export Preview Report",
        "",
        f"- Status: `{report['status']}`",
        f"- Dataset: `{report['dataset_file']}`",
        f"- Demo: `{report['demo_name']}`",
        f"- Frames: `{report['frame_count']}`",
        f"- FPS: `{report['fps']}`",
        "",
        "## Outputs",
        "",
        "| Artifact | Path | Bytes |",
        "|---|---|---:|",
    ]
    for name, meta in report["outputs"].items():
        lines.append(f"| `{name}` | `{meta['path']}` | `{meta.get('bytes', 0)}` |")

    lines.extend(["", "## Videos", "", "| Video | Readable | Frames | Size |", "|---|---|---:|---|"])
    for name, meta in report["videos"].items():
        lines.append(
            f"| `{name}` | `{meta['readable'] and meta['first_frame_readable']}` | "
            f"`{meta['frame_count']}/{meta['expected_frames']}` | `{meta['width']}x{meta['height']}` |"
        )

    lines.extend(["", "## Image Checks", "", "| Camera | Shape | First Std | Last Std | First/Last Diff |", "|---|---:|---:|---:|---:|"])
    for camera, meta in report["image_checks"].items():
        lines.append(
            f"| `{camera}` | `{meta['shape']}` | `{meta['first_std']:.5f}` | "
            f"`{meta['last_std']:.5f}` | `{meta['first_last_mean_abs_diff']:.5f}` |"
        )

    lines.extend(["", "## Issues", ""])
    if report["issues"]:
        for issue in report["issues"]:
            lines.append(f"- {issue}")
    else:
        lines.append("- No export issues.")
    lines.append("")
    return "\n".join(lines)


def export_preview(args: argparse.Namespace) -> dict[str, Any]:
    dataset_file = (ROOT / args.dataset_file).resolve() if not Path(args.dataset_file).is_absolute() else Path(args.dataset_file)
    session = setup_logging(args.session_name)
    log_environment(session, {"stage": "PHYS-9.0", "dataset_file": str(dataset_file), "demo_name": args.demo_name})

    try:
        demo = _read_demo(dataset_file, args.demo_name)
        actions = demo["actions"]
        state = demo["state"]
        images = {camera: _ensure_rgb_uint8(frames, camera) for camera, frames in demo["images"].items()}
        issues = _validate_shapes(actions, state, images)
        frame_count = int(actions.shape[0])
        times = np.arange(frame_count, dtype=np.float64) / float(args.fps)

        first_images = {camera: frames[0] for camera, frames in images.items()}
        last_images = {camera: frames[-1] for camera, frames in images.items()}
        save_multiview_grid(first_images, session.root / "first_grid.png", title=f"{args.demo_name}_first")
        save_multiview_grid(last_images, session.root / "last_grid.png", title=f"{args.demo_name}_last")

        joint_csv = session.root / "joint_trajectory.csv"
        action_csv = session.root / "action_trajectory.csv"
        npz_path = session.root / "trajectory.npz"
        _write_csv(joint_csv, times, state, JOINT_NAMES)
        _write_csv(action_csv, times, actions, JOINT_NAMES)
        np.savez_compressed(
            npz_path,
            time_sec=times,
            joint_names=np.asarray(JOINT_NAMES),
            observation_state=state,
            actions=actions,
        )

        videos: dict[str, Any] = {}
        for camera in CAMERAS:
            videos[camera] = _write_mp4(session.root / f"{camera}.mp4", images[camera], args.fps)
        multiview_frames = _make_multiview_frames(images)
        videos["multiview"] = _write_mp4(session.root / "multiview.mp4", multiview_frames, args.fps)

        image_checks: dict[str, Any] = {}
        for camera, frames in images.items():
            first = frames[0]
            last = frames[-1]
            first_stats = image_stats(first)
            last_stats = image_stats(last)
            image_checks[camera] = {
                "shape": list(frames.shape),
                "dtype": str(frames.dtype),
                "first_std": first_stats["std"],
                "last_std": last_stats["std"],
                "first_unique_sample_count": first_stats["unique_sample_count"],
                "last_unique_sample_count": last_stats["unique_sample_count"],
                "first_last_mean_abs_diff": mean_abs_diff(first, last),
            }
            if first_stats["std"] < args.min_image_std or last_stats["std"] < args.min_image_std:
                issues.append(f"{camera} appears blank: first_std={first_stats['std']:.5f}, last_std={last_stats['std']:.5f}")

        for name, meta in videos.items():
            if meta["bytes"] <= 0:
                issues.append(f"{name}.mp4 is empty")
            if not meta["readable"] or not meta["first_frame_readable"]:
                issues.append(f"{name}.mp4 is not readable by OpenCV")
            if abs(meta["frame_count"] - meta["expected_frames"]) > args.frame_tolerance:
                issues.append(f"{name}.mp4 frame_count={meta['frame_count']} expected={meta['expected_frames']}")

        outputs = {
            "joint_trajectory_csv": {"path": str(joint_csv), "bytes": joint_csv.stat().st_size},
            "action_trajectory_csv": {"path": str(action_csv), "bytes": action_csv.stat().st_size},
            "trajectory_npz": {"path": str(npz_path), "bytes": npz_path.stat().st_size},
            "first_grid": {"path": str(session.root / "first_grid.png"), "bytes": (session.root / "first_grid.png").stat().st_size},
            "last_grid": {"path": str(session.root / "last_grid.png"), "bytes": (session.root / "last_grid.png").stat().st_size},
        }
        outputs.update({f"{name}_mp4": {"path": meta["path"], "bytes": meta["bytes"]} for name, meta in videos.items()})

        report = {
            "status": "PASS" if not issues else "FAIL",
            "dataset_file": str(dataset_file),
            "demo_name": args.demo_name,
            "attrs": demo["attrs"],
            "fps": float(args.fps),
            "frame_count": frame_count,
            "actions_shape": list(actions.shape),
            "state_shape": list(state.shape),
            "joint_names": JOINT_NAMES,
            "videos": videos,
            "outputs": outputs,
            "image_checks": image_checks,
            "issues": issues,
        }
        (session.root / "export_report.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        (session.root / "export_report.md").write_text(_render_markdown(report), encoding="utf-8")
        session.data.info("report=%s", json.dumps(report, sort_keys=True))

        if issues:
            mark_fail(session, "FAIL_PHYS90_HDF5_EXPORT_PREVIEW", "; ".join(issues))
            raise RuntimeError("PHYS-9.0 export failed: " + "; ".join(issues))
        mark_pass(session, "PASS_PHYS90_HDF5_EXPORT_PREVIEW", "PHYS-9.0 HDF5 export preview passed")
        return report
    except Exception as exc:
        session.run.error("PHYS-9.0 failed: %s", exc)
        session.run.error("%s", traceback.format_exc())
        mark_fail(session, "FAIL_PHYS90_HDF5_EXPORT_PREVIEW", str(exc))
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-name", default="session_phys90_hdf5_export_preview_v1")
    parser.add_argument("--dataset-file", default="datasets/raw_hdf5/pickcube_episode_phys84.hdf5")
    parser.add_argument("--demo-name", default="demo_0")
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--min-image-std", type=float, default=2.0)
    parser.add_argument("--frame-tolerance", type=int, default=1)
    return parser.parse_args()


def main() -> None:
    export_preview(parse_args())


if __name__ == "__main__":
    main()
