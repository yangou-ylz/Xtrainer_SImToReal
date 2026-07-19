#!/usr/bin/env python3
"""Generate a compact quality report for one PHYS batch run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import traceback

import h5py
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from phys_data_gen.action_mapping import check_leisaac16_gripper_symmetry
from phys_data_gen.logging_utils import log_environment, mark_fail, mark_pass, setup_logging


def summarize_hdf5(path: Path) -> dict:
    summary = {"path": str(path), "bytes": path.stat().st_size, "demos": [], "total_samples": 0}
    with h5py.File(path, "r") as h5:
        for demo_name in sorted(h5["data"].keys()):
            demo = h5["data"][demo_name]
            actions = np.asarray(demo["actions"])
            symmetry = check_leisaac16_gripper_symmetry(actions)
            demo_summary = {
                "name": demo_name,
                "num_samples": int(demo.attrs.get("num_samples", actions.shape[0])),
                "success": _jsonable(demo.attrs.get("success", None)),
                "seed": _jsonable(demo.attrs.get("seed", None)),
                "action_shape": list(actions.shape),
                "action_min": float(np.min(actions)),
                "action_max": float(np.max(actions)),
                "gripper_symmetry": {
                    "passed": symmetry.passed,
                    "left_max_abs": symmetry.left_max_abs,
                    "right_max_abs": symmetry.right_max_abs,
                },
                "images": {},
            }
            for key in ("obs/top", "obs/left_wrist", "obs/right_wrist"):
                data = demo[key]
                preview = data[: min(4, data.shape[0])]
                demo_summary["images"][key] = {
                    "shape": list(data.shape),
                    "dtype": str(data.dtype),
                    "std_first_frames": float(np.std(preview)),
                }
            summary["demos"].append(demo_summary)
            summary["total_samples"] += demo_summary["num_samples"]
    return summary


def _jsonable(value):
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def render_markdown(report: dict) -> str:
    hdf5 = report["hdf5"]
    lerobot = report["lerobot_conversion"]
    lines = [
        "# PHYS-7 Batch Quality Report",
        "",
        f"- Status: `{report['status']}`",
        f"- Profile: `{report['profile']}`",
        f"- Seed: `{report['seed']}`",
        f"- HDF5: `{hdf5['path']}`",
        f"- HDF5 bytes: `{hdf5['bytes']}`",
        f"- HDF5 demos: `{len(hdf5['demos'])}`",
        f"- HDF5 samples: `{hdf5['total_samples']}`",
        f"- LeRobot root: `{lerobot.get('output_root', '')}`",
        f"- LeRobot episodes: `{lerobot.get('inspection', {}).get('num_episodes', '')}`",
        f"- LeRobot frames: `{lerobot.get('inspection', {}).get('num_frames', '')}`",
        "",
        "## HDF5 Demos",
        "",
        "| Demo | Samples | Success | Action Min | Action Max | Gripper Symmetry |",
        "|---|---:|---|---:|---:|---|",
    ]
    for demo in hdf5["demos"]:
        sym = demo["gripper_symmetry"]
        lines.append(
            f"| `{demo['name']}` | `{demo['num_samples']}` | `{demo['success']}` | "
            f"`{demo['action_min']:.5f}` | `{demo['action_max']:.5f}` | `{sym['passed']}` |"
        )
    lines.extend(["", "## Image Checks", "", "| Demo | Camera | Shape | Dtype | Std First Frames |", "|---|---|---:|---|---:|"])
    for demo in hdf5["demos"]:
        for key, meta in demo["images"].items():
            lines.append(
                f"| `{demo['name']}` | `{key}` | `{meta['shape']}` | `{meta['dtype']}` | "
                f"`{meta['std_first_frames']:.5f}` |"
            )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-name", required=True)
    parser.add_argument("--profile", default="minimal_pickcube")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--hdf5-file", required=True)
    parser.add_argument("--validator-json", required=True)
    parser.add_argument("--lerobot-report-json", required=True)
    args = parser.parse_args()

    session = setup_logging(session_name=args.session_name)
    hdf5_path = Path(args.hdf5_file)
    if not hdf5_path.is_absolute():
        hdf5_path = ROOT / hdf5_path
    validator_json = Path(args.validator_json)
    if not validator_json.is_absolute():
        validator_json = ROOT / validator_json
    lerobot_report_json = Path(args.lerobot_report_json)
    if not lerobot_report_json.is_absolute():
        lerobot_report_json = ROOT / lerobot_report_json

    session.run.info("phys70_quality_report_start hdf5=%s", hdf5_path)
    log_environment(session, extra={"stage": "PHYS-7", "profile": args.profile, "seed": args.seed})

    try:
        validator = json.loads(validator_json.read_text(encoding="utf-8"))
        lerobot = json.loads(lerobot_report_json.read_text(encoding="utf-8"))
        hdf5 = summarize_hdf5(hdf5_path)
        issues = []
        if not validator.get("passed", False):
            issues.append("hdf5 validator did not pass")
        if lerobot.get("status") != "PASS":
            issues.append("lerobot conversion did not pass")
        if hdf5["total_samples"] <= 0:
            issues.append("no hdf5 samples")
        for demo in hdf5["demos"]:
            if not demo["gripper_symmetry"]["passed"]:
                issues.append(f"{demo['name']} gripper symmetry failed")
            for camera, meta in demo["images"].items():
                if meta["std_first_frames"] < 2.0:
                    issues.append(f"{demo['name']} {camera} image std too low")

        report = {
            "status": "FAIL" if issues else "PASS",
            "profile": args.profile,
            "seed": args.seed,
            "hdf5": hdf5,
            "validator": validator,
            "lerobot_conversion": lerobot,
            "issues": issues,
        }
        (session.root / "batch_quality_report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (session.root / "batch_quality_report.md").write_text(render_markdown(report), encoding="utf-8")
        session.data.info("batch_quality_report=%s", json.dumps(report, sort_keys=True))

        if issues:
            mark_fail(session, "FAIL_PHYS70_BATCH_QUALITY_REPORT", "; ".join(issues))
            return 10
        mark_pass(session, "PASS_PHYS70_BATCH_QUALITY_REPORT", "batch quality report passed")
        session.run.info("phys70_quality_report_ok")
        return 0
    except BaseException as exc:
        session.run.error("phys70_quality_report_failed type=%s error=%r", type(exc).__name__, exc)
        session.run.error("traceback:\n%s", traceback.format_exc())
        mark_fail(session, "FAIL_PHYS70_BATCH_QUALITY_REPORT", f"{type(exc).__name__}: {exc}")
        return 20


if __name__ == "__main__":
    raise SystemExit(main())
