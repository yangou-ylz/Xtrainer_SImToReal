#!/usr/bin/env python3
"""User-friendly HDF5 export entrypoint.

Edit the USER SETTINGS block below, then run:

    python3 scripts/export_episode.py
"""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace


# =========================
# USER SETTINGS
# =========================

# Use "AUTO_LATEST" to export the newest HDF5 under datasets/raw_hdf5/.
DATASET_FILE = "AUTO_LATEST"

# Usually this stays "demo_0".
DEMO_NAME = "demo_0"

# Output session names. Use "AUTO" to generate names from the HDF5 filename.
EXPORT_SESSION_NAME = "AUTO"
QUALITY_SESSION_NAME = "AUTO"

# Video and quality settings.
FPS = 30.0
RUN_QUALITY_GATE = True

# Quality gate thresholds.
MIN_FRAMES = 120
MIN_ENDPOINT_DISPLACEMENT = 0.03
MIN_CURRENT_ENDPOINT_DISPLACEMENT = 0.03
MIN_JOINT_DELTA = 0.01
MIN_GRIPPER_RANGE = 0.02
MIN_IMAGE_STD = 2.0
MIN_IMAGE_DIFF = 0.2
FRAME_TOLERANCE = 1


# =========================
# IMPLEMENTATION
# =========================

ROOT = Path(__file__).resolve().parents[1]
ENV_NAME = "xtrainer_VLA"


def _latest_hdf5() -> Path:
    candidates = sorted((ROOT / "datasets/raw_hdf5").glob("*.hdf5"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError("No HDF5 files found under datasets/raw_hdf5/")
    return candidates[0]


def _dataset_path() -> Path:
    if DATASET_FILE == "AUTO_LATEST":
        return _latest_hdf5()
    path = Path(DATASET_FILE)
    return path if path.is_absolute() else ROOT / path


def _session_name(prefix: str, configured: str, dataset: Path) -> str:
    if configured != "AUTO":
        return configured
    return f"{prefix}_{dataset.stem}"


def _run_in_conda() -> int:
    command = (
        f"cd {str(ROOT)!r} && "
        "source scripts/common_env.sh && "
        "load_conda && "
        "sanitize_for_isaac && "
        f"conda run -n {ENV_NAME} python scripts/export_episode.py --worker"
    )
    return subprocess.call(["bash", "-lc", command])


def _worker() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(ROOT / "scripts"))

    from phys90_hdf5_export_preview import export_preview
    from phys100_endpoint_dataset_quality import run_quality_gate

    dataset = _dataset_path()
    export_session = _session_name("export", EXPORT_SESSION_NAME, dataset)
    quality_session = _session_name("quality", QUALITY_SESSION_NAME, dataset)

    print("============================================================")
    print("Export X-Trainer HDF5 episode")
    print("============================================================")
    print(f"Dataset : {dataset}")
    print(f"Export  : logs/{export_session}/")
    print(f"Quality : logs/{quality_session}/" if RUN_QUALITY_GATE else "Quality : skipped")

    export_args = SimpleNamespace(
        session_name=export_session,
        dataset_file=str(dataset),
        demo_name=DEMO_NAME,
        fps=FPS,
        min_image_std=MIN_IMAGE_STD,
        frame_tolerance=FRAME_TOLERANCE,
    )
    export_preview(export_args)

    if RUN_QUALITY_GATE:
        quality_args = SimpleNamespace(
            session_name=quality_session,
            dataset_file=str(dataset),
            export_session=export_session,
            export_report="",
            require_success=False,
            min_frames=MIN_FRAMES,
            min_endpoint_displacement=MIN_ENDPOINT_DISPLACEMENT,
            min_current_endpoint_displacement=MIN_CURRENT_ENDPOINT_DISPLACEMENT,
            min_joint_delta=MIN_JOINT_DELTA,
            min_gripper_range=MIN_GRIPPER_RANGE,
            min_image_std=MIN_IMAGE_STD,
            min_image_diff=MIN_IMAGE_DIFF,
            frame_tolerance=FRAME_TOLERANCE,
        )
        run_quality_gate(quality_args)

    print("")
    print("Export finished.")
    print(f"Multi-view video : {ROOT / 'logs' / export_session / 'multiview.mp4'}")
    print(f"Trajectory       : {ROOT / 'logs' / export_session / 'trajectory.npz'}")
    if RUN_QUALITY_GATE:
        print(f"Quality report   : {ROOT / 'logs' / quality_session / 'endpoint_dataset_quality_report.md'}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not args.worker:
        return _run_in_conda()
    _worker()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
