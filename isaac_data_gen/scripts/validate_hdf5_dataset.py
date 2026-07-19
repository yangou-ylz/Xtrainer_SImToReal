#!/usr/bin/env python3
"""Validate X-Trainer LeIsaac HDF5 datasets."""

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

from phys_data_gen.dataset_validation import render_markdown_report, validate_hdf5_dataset
from phys_data_gen.logging_utils import log_environment, mark_fail, mark_pass, setup_logging


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset_file")
    parser.add_argument("--session-name", default=None)
    parser.add_argument("--require-success", action="store_true")
    parser.add_argument("--gripper-tolerance", type=float, default=1e-5)
    args = parser.parse_args()

    session = setup_logging(session_name=args.session_name)
    dataset_path = Path(args.dataset_file)
    if not dataset_path.is_absolute():
        dataset_path = ROOT / dataset_path
    session.run.info("validate_hdf5_dataset_start dataset=%s require_success=%s", dataset_path, args.require_success)
    log_environment(session, extra={"stage": "PHYS-3.1", "dataset_file": str(dataset_path)})

    try:
        result = validate_hdf5_dataset(
            dataset_path,
            require_success=args.require_success,
            gripper_tolerance=args.gripper_tolerance,
        )
        report = render_markdown_report(result)
        report_path = session.root / "dataset_validation_report.md"
        json_path = session.root / "dataset_validation_report.json"
        report_path.write_text(report, encoding="utf-8")
        json_path.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        session.run.info("validation_report=%s", report_path)
        session.run.info("validation_json=%s", json_path)
        session.data.info("validation_result=%s", json.dumps(result.to_dict(), sort_keys=True))

        if result.passed:
            mark_pass(session, "PASS_PHYS31_HDF5_VALIDATION", "HDF5 validator passed")
            session.run.info("validate_hdf5_dataset_ok")
            return 0
        mark_fail(session, "FAIL_PHYS31_HDF5_VALIDATION", "HDF5 validator failed")
        return 10
    except BaseException as exc:
        session.run.error("validate_hdf5_dataset_exception type=%s error=%r", type(exc).__name__, exc)
        session.run.error("traceback:\n%s", traceback.format_exc())
        mark_fail(session, "FAIL_PHYS31_HDF5_VALIDATION", f"{type(exc).__name__}: {exc}")
        return 20


if __name__ == "__main__":
    raise SystemExit(main())
