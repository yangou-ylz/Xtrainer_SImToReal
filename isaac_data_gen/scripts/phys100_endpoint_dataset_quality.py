#!/usr/bin/env python3
"""Quality gate for endpoint-control X-Trainer HDF5 episodes."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys
import traceback
from typing import Any

import h5py
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from phys_data_gen.dataset_validation import render_markdown_report, validate_hdf5_dataset
from phys_data_gen.image_validation import CAMERAS, image_stats, mean_abs_diff
from phys_data_gen.logging_utils import log_environment, mark_fail, mark_pass, setup_logging


EXPECTED_ENDPOINT_DATASETS = {
    "obs/endpoint_action18": (18,),
    "obs/target_eef_pose": (8,),
    "obs/current_eef_pose": (7,),
}

EXPECTED_EXPORT_ARTIFACTS = (
    "top_mp4",
    "left_wrist_mp4",
    "right_wrist_mp4",
    "multiview_mp4",
    "joint_trajectory_csv",
    "action_trajectory_csv",
    "trajectory_npz",
    "first_grid",
    "last_grid",
)


def _jsonable(value: Any) -> Any:
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, np.ndarray):
        return value.tolist()
    return value


def _resolve(path: str | Path) -> Path:
    path = Path(path)
    return path if path.is_absolute() else (ROOT / path)


def _range(values: np.ndarray) -> float:
    return float(np.max(values) - np.min(values))


def _max_abs_delta(values: np.ndarray) -> float:
    if len(values) < 2:
        return 0.0
    return float(np.max(np.abs(values[-1] - values[0])))


def _load_export_report(path: Path | None, export_session: str | None) -> tuple[dict[str, Any] | None, Path | None]:
    if path is None and export_session:
        path = ROOT / "logs" / export_session / "export_report.json"
    if path is None:
        return None, None
    path = _resolve(path)
    if not path.exists():
        return None, path
    return json.loads(path.read_text(encoding="utf-8")), path


def _check_hdf5(args: argparse.Namespace, dataset_file: Path) -> dict[str, Any]:
    report: dict[str, Any] = {"demos": [], "issues": []}
    if not dataset_file.exists():
        report["issues"].append(f"dataset file does not exist: {dataset_file}")
        return report

    with h5py.File(dataset_file, "r") as h5:
        if "data" not in h5:
            report["issues"].append("missing /data group")
            return report
        demo_names = sorted(k for k in h5["data"].keys() if k.startswith("demo_"))
        if not demo_names:
            report["issues"].append("no demo_* groups found")
            return report
        for demo_name in demo_names:
            demo = h5["data"][demo_name]
            demo_path = f"/data/{demo_name}"
            demo_report: dict[str, Any] = {
                "name": demo_name,
                "attrs": {key: _jsonable(value) for key, value in demo.attrs.items()},
                "checks": {},
                "image_checks": {},
                "issues": [],
            }
            num_samples = int(demo.attrs.get("num_samples", 0))
            demo_report["num_samples"] = num_samples
            if num_samples < args.min_frames:
                demo_report["issues"].append(f"{demo_path} has {num_samples} frames, expected >= {args.min_frames}")

            for rel_path, trailing_shape in EXPECTED_ENDPOINT_DATASETS.items():
                full_path = f"{demo_path}/{rel_path}"
                if rel_path not in demo:
                    demo_report["issues"].append(f"missing endpoint dataset {full_path}")
                    continue
                data = np.asarray(demo[rel_path])
                demo_report["checks"][rel_path] = {"shape": list(data.shape), "dtype": str(data.dtype)}
                if data.shape[0] != num_samples:
                    demo_report["issues"].append(f"{full_path} length {data.shape[0]} != num_samples {num_samples}")
                if data.shape[1:] != trailing_shape:
                    demo_report["issues"].append(f"{full_path} trailing shape {data.shape[1:]} != {trailing_shape}")
                if np.issubdtype(data.dtype, np.floating) and not np.all(np.isfinite(data)):
                    demo_report["issues"].append(f"{full_path} contains NaN or Inf")

            if "actions" in demo:
                actions = np.asarray(demo["actions"], dtype=np.float32)
                joint_delta = _max_abs_delta(actions)
                right_gripper_range = _range(actions[:, 15]) if actions.ndim == 2 and actions.shape[1] == 16 else 0.0
                demo_report["checks"]["actions_motion"] = {
                    "shape": list(actions.shape),
                    "max_abs_first_last_delta": joint_delta,
                    "right_gripper_range": right_gripper_range,
                }
                if joint_delta < args.min_joint_delta:
                    demo_report["issues"].append(f"joint target motion too small: {joint_delta:.6f} < {args.min_joint_delta}")
                if right_gripper_range < args.min_gripper_range:
                    demo_report["issues"].append(
                        f"right gripper range too small: {right_gripper_range:.6f} < {args.min_gripper_range}"
                    )

            if "obs/target_eef_pose" in demo:
                target_pose = np.asarray(demo["obs/target_eef_pose"], dtype=np.float32)
                target_disp = float(np.linalg.norm(target_pose[-1, :3] - target_pose[0, :3]))
                demo_report["checks"]["target_endpoint_motion"] = {"displacement_m": target_disp}
                if target_disp < args.min_endpoint_displacement:
                    demo_report["issues"].append(
                        f"target endpoint displacement too small: {target_disp:.6f} < {args.min_endpoint_displacement}"
                    )

            if "obs/current_eef_pose" in demo:
                current_pose = np.asarray(demo["obs/current_eef_pose"], dtype=np.float32)
                current_disp = float(np.linalg.norm(current_pose[-1, :3] - current_pose[0, :3]))
                demo_report["checks"]["current_endpoint_motion"] = {"displacement_m": current_disp}
                if current_disp < args.min_current_endpoint_displacement:
                    demo_report["issues"].append(
                        "current endpoint displacement too small: "
                        f"{current_disp:.6f} < {args.min_current_endpoint_displacement}"
                    )

            for camera in CAMERAS:
                key = f"obs/{camera}"
                if key not in demo:
                    demo_report["issues"].append(f"missing camera dataset {demo_path}/{key}")
                    continue
                frames = np.asarray(demo[key])
                first = frames[0]
                last = frames[-1]
                first_stats = image_stats(first)
                last_stats = image_stats(last)
                diff = mean_abs_diff(first, last)
                demo_report["image_checks"][camera] = {
                    "shape": list(frames.shape),
                    "dtype": str(frames.dtype),
                    "first_std": first_stats["std"],
                    "last_std": last_stats["std"],
                    "first_last_mean_abs_diff": diff,
                }
                if frames.shape[0] != num_samples:
                    demo_report["issues"].append(f"{demo_path}/{key} length {frames.shape[0]} != num_samples {num_samples}")
                if frames.shape[1:] != (480, 640, 3) or frames.dtype != np.uint8:
                    demo_report["issues"].append(f"{demo_path}/{key} expected uint8 [T,480,640,3], got {frames.shape} {frames.dtype}")
                if first_stats["std"] < args.min_image_std or last_stats["std"] < args.min_image_std:
                    demo_report["issues"].append(
                        f"{camera} appears blank: first_std={first_stats['std']:.5f}, last_std={last_stats['std']:.5f}"
                    )
                if diff < args.min_image_diff:
                    demo_report["issues"].append(f"{camera} first/last image diff too small: {diff:.6f} < {args.min_image_diff}")

            report["demos"].append(demo_report)
            report["issues"].extend(demo_report["issues"])
    return report


def _check_export_report(
    export_report: dict[str, Any] | None,
    export_report_path: Path | None,
    args: argparse.Namespace,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "path": str(export_report_path) if export_report_path else "",
        "status": "",
        "videos": {},
        "artifacts": {},
        "issues": [],
    }
    if export_report is None:
        report["issues"].append(f"export report is missing: {export_report_path or '<not provided>'}")
        return report
    report["status"] = str(export_report.get("status", ""))
    if export_report.get("status") != "PASS":
        report["issues"].append(f"export report status is not PASS: {export_report.get('status')}")

    videos = export_report.get("videos", {})
    for name, meta in videos.items():
        video_ok = bool(meta.get("readable")) and bool(meta.get("first_frame_readable"))
        frame_ok = abs(int(meta.get("frame_count", 0)) - int(meta.get("expected_frames", -1))) <= args.frame_tolerance
        size_ok = int(meta.get("bytes", 0)) > 0
        report["videos"][name] = {"readable": video_ok, "frame_count_ok": frame_ok, "size_ok": size_ok, **meta}
        if not video_ok or not frame_ok or not size_ok:
            report["issues"].append(f"video check failed for {name}: readable={video_ok}, frame_ok={frame_ok}, size_ok={size_ok}")

    outputs = export_report.get("outputs", {})
    for artifact in EXPECTED_EXPORT_ARTIFACTS:
        meta = outputs.get(artifact)
        if not meta:
            report["issues"].append(f"missing export artifact in report: {artifact}")
            continue
        path = Path(str(meta.get("path", "")))
        exists = path.exists()
        bytes_ok = int(meta.get("bytes", 0)) > 0 and exists and path.stat().st_size > 0
        report["artifacts"][artifact] = {"path": str(path), "exists": exists, "bytes_ok": bytes_ok, "bytes": int(meta.get("bytes", 0))}
        if not bytes_ok:
            report["issues"].append(f"export artifact missing or empty: {artifact} ({path})")
    return report


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# PHYS-10.0/10.2 Endpoint Dataset Quality Report",
        "",
        f"- Status: `{report['status']}`",
        f"- Usable: `{report['usable']}`",
        f"- Dataset: `{report['dataset_file']}`",
        f"- Export report: `{report['export_report_path']}`",
        f"- Validator passed: `{report['validator']['passed']}`",
        f"- Total frames: `{report['validator']['total_samples']}`",
        "",
        "## Endpoint Checks",
        "",
        "| Demo | Frames | Target disp m | Current disp m | Joint delta | Gripper range | Issues |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for demo in report["hdf5"]["demos"]:
        checks = demo["checks"]
        lines.append(
            f"| `{demo['name']}` | `{demo['num_samples']}` | "
            f"`{checks.get('target_endpoint_motion', {}).get('displacement_m', 0.0):.6f}` | "
            f"`{checks.get('current_endpoint_motion', {}).get('displacement_m', 0.0):.6f}` | "
            f"`{checks.get('actions_motion', {}).get('max_abs_first_last_delta', 0.0):.6f}` | "
            f"`{checks.get('actions_motion', {}).get('right_gripper_range', 0.0):.6f}` | "
            f"`{len(demo['issues'])}` |"
        )

    lines.extend(["", "## Image Checks", "", "| Demo | Camera | Shape | First std | Last std | First/last diff |", "|---|---|---:|---:|---:|---:|"])
    for demo in report["hdf5"]["demos"]:
        for camera, meta in demo["image_checks"].items():
            lines.append(
                f"| `{demo['name']}` | `{camera}` | `{meta['shape']}` | `{meta['first_std']:.5f}` | "
                f"`{meta['last_std']:.5f}` | `{meta['first_last_mean_abs_diff']:.5f}` |"
            )

    lines.extend(["", "## Export Checks", "", "| Artifact | Exists | Bytes OK | Path |", "|---|---|---|---|"])
    for name, meta in report["export"]["artifacts"].items():
        lines.append(f"| `{name}` | `{meta['exists']}` | `{meta['bytes_ok']}` | `{meta['path']}` |")

    lines.extend(["", "## Issues", ""])
    if report["issues"]:
        for issue in report["issues"]:
            lines.append(f"- {issue}")
    else:
        lines.append("- No quality gate issues.")
    lines.append("")
    return "\n".join(lines)


def run_quality_gate(args: argparse.Namespace) -> dict[str, Any]:
    dataset_file = _resolve(args.dataset_file)
    export_report_arg = _resolve(args.export_report) if args.export_report else None
    session = setup_logging(args.session_name, console=not args.no_raise_on_fail)
    log_environment(
        session,
        {
            "stage": "PHYS-10.0/10.2",
            "dataset_file": str(dataset_file),
            "export_report": str(export_report_arg or ""),
            "export_session": args.export_session or "",
        },
    )

    try:
        for handler in list(session.data.handlers):
            if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
                session.data.removeHandler(handler)
        validator = validate_hdf5_dataset(dataset_file, require_success=args.require_success)
        hdf5_report = _check_hdf5(args, dataset_file)
        export_report, export_report_path = _load_export_report(export_report_arg, args.export_session)
        export_checks = _check_export_report(export_report, export_report_path, args)
        issues: list[str] = []
        if not validator.passed:
            issues.append("base HDF5 validator failed")
        issues.extend(f"hdf5: {issue}" for issue in hdf5_report["issues"])
        issues.extend(f"export: {issue}" for issue in export_checks["issues"])

        report = {
            "status": "PASS" if not issues else "FAIL",
            "usable": not issues,
            "dataset_file": str(dataset_file),
            "export_report_path": str(export_report_path or ""),
            "thresholds": {
                "min_frames": args.min_frames,
                "min_endpoint_displacement": args.min_endpoint_displacement,
                "min_current_endpoint_displacement": args.min_current_endpoint_displacement,
                "min_joint_delta": args.min_joint_delta,
                "min_gripper_range": args.min_gripper_range,
                "min_image_std": args.min_image_std,
                "min_image_diff": args.min_image_diff,
            },
            "validator": validator.to_dict(),
            "hdf5": hdf5_report,
            "export": export_checks,
            "issues": issues,
        }
        (session.root / "dataset_validation_report.json").write_text(json.dumps(validator.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        (session.root / "dataset_validation_report.md").write_text(render_markdown_report(validator), encoding="utf-8")
        (session.root / "endpoint_dataset_quality_report.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        (session.root / "endpoint_dataset_quality_report.md").write_text(_render_markdown(report), encoding="utf-8")
        session.data.info("endpoint_quality_report=%s", json.dumps(report, sort_keys=True))

        if issues:
            mark_fail(session, "FAIL_PHYS100_ENDPOINT_DATASET_QUALITY", "; ".join(issues))
            if args.no_raise_on_fail:
                session.run.warning("PHYS-10 quality gate returned soft failure: %s", "; ".join(issues))
                return report
            raise RuntimeError("PHYS-10 endpoint dataset quality failed: " + "; ".join(issues))
        mark_pass(session, "PASS_PHYS100_ENDPOINT_DATASET_QUALITY", "PHYS-10 endpoint dataset quality gate passed")
        return report
    except Exception as exc:
        session.run.error("PHYS-10 quality gate failed: %s", exc)
        session.run.error("%s", traceback.format_exc())
        mark_fail(session, "FAIL_PHYS100_ENDPOINT_DATASET_QUALITY", str(exc))
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-name", default="session_phys100_endpoint_dataset_quality_v1")
    parser.add_argument("--dataset-file", default="datasets/raw_hdf5/phys93_endpoint_episode.hdf5")
    parser.add_argument("--export-session", default="session_phys93_endpoint_keyboard_record_v1_export")
    parser.add_argument("--export-report", default="")
    parser.add_argument("--require-success", action="store_true")
    parser.add_argument("--min-frames", type=int, default=120)
    parser.add_argument("--min-endpoint-displacement", type=float, default=0.03)
    parser.add_argument("--min-current-endpoint-displacement", type=float, default=0.03)
    parser.add_argument("--min-joint-delta", type=float, default=0.01)
    parser.add_argument("--min-gripper-range", type=float, default=0.02)
    parser.add_argument("--min-image-std", type=float, default=2.0)
    parser.add_argument("--min-image-diff", type=float, default=0.2)
    parser.add_argument("--frame-tolerance", type=int, default=1)
    parser.add_argument(
        "--no-raise-on-fail",
        action="store_true",
        help="Write FAIL marker/report without printing a Python traceback for expected quality-gate failures.",
    )
    return parser.parse_args()


def main() -> None:
    run_quality_gate(parse_args())


if __name__ == "__main__":
    main()
