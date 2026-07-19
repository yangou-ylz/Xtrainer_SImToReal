"""HDF5 dataset validation utilities for X-Trainer LeIsaac recordings."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import h5py
import numpy as np


REQUIRED_DATASETS = {
    "actions": (16,),
    "processed_actions": (16,),
    "obs/actions": (16,),
    "obs/left_joint_pos_rel": (8,),
    "obs/right_joint_pos_rel": (8,),
    "obs/top": (480, 640, 3),
    "obs/left_wrist": (480, 640, 3),
    "obs/right_wrist": (480, 640, 3),
}

GRIPPER_PAIRS = {
    "left": (6, 7),
    "right": (14, 15),
}


@dataclass
class DatasetIssue:
    level: str
    path: str
    message: str


@dataclass
class DatasetValidationResult:
    path: Path
    passed: bool = True
    demos: list[str] = field(default_factory=list)
    total_samples: int = 0
    datasets: dict[str, dict[str, Any]] = field(default_factory=dict)
    issues: list[DatasetIssue] = field(default_factory=list)

    def add_issue(self, level: str, path: str, message: str) -> None:
        self.issues.append(DatasetIssue(level=level, path=path, message=message))
        if level == "error":
            self.passed = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "passed": self.passed,
            "demos": self.demos,
            "total_samples": self.total_samples,
            "datasets": self.datasets,
            "issues": [issue.__dict__ for issue in self.issues],
        }


def _jsonable(value):
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _check_finite(result: DatasetValidationResult, dataset_path: str, data: np.ndarray) -> None:
    if np.issubdtype(data.dtype, np.floating):
        if not np.all(np.isfinite(data)):
            result.add_issue("error", dataset_path, "contains NaN or Inf")


def _check_image(result: DatasetValidationResult, dataset_path: str, data: np.ndarray) -> None:
    if data.dtype != np.uint8:
        result.add_issue("error", dataset_path, f"image dtype must be uint8, got {data.dtype}")
    std = float(np.std(data[: min(len(data), 4)]))
    if std < 2.0:
        result.add_issue("error", dataset_path, f"image appears blank, std={std:.4f}")


def _check_gripper_symmetry(
    result: DatasetValidationResult,
    dataset_path: str,
    data: np.ndarray,
    tolerance: float,
) -> None:
    if data.shape[-1] != 16:
        return
    for side, (neg_idx, pos_idx) in GRIPPER_PAIRS.items():
        diff = np.max(np.abs(data[:, neg_idx] + data[:, pos_idx]))
        if diff > tolerance:
            result.add_issue("error", dataset_path, f"{side} gripper pair is not symmetric, max |J*_7+J*_8|={diff:.6g}")


def validate_hdf5_dataset(
    path: str | Path,
    *,
    require_success: bool = False,
    gripper_tolerance: float = 1e-5,
) -> DatasetValidationResult:
    """Validate the project HDF5 schema and basic data quality."""

    path = Path(path)
    result = DatasetValidationResult(path=path)
    if not path.exists():
        result.add_issue("error", str(path), "file does not exist")
        return result

    with h5py.File(path, "r") as h5:
        if "data" not in h5:
            result.add_issue("error", "/data", "missing data group")
            return result

        data_group = h5["data"]
        demos = sorted(k for k in data_group.keys() if k.startswith("demo_"))
        result.demos = demos
        if not demos:
            result.add_issue("error", "/data", "no demo_* groups found")
            return result

        for demo_name in demos:
            demo = data_group[demo_name]
            demo_path = f"/data/{demo_name}"
            num_samples = int(demo.attrs.get("num_samples", 0))
            result.total_samples += num_samples
            if num_samples <= 0:
                result.add_issue("error", demo_path, f"invalid num_samples={num_samples}")

            success_attr = demo.attrs.get("success", None)
            if require_success and not bool(success_attr):
                result.add_issue("error", demo_path, f"success attr is not true: {success_attr}")
            elif success_attr is None:
                result.add_issue("warning", demo_path, "success attr missing; acceptable for smoke datasets only")

            for rel_path, trailing_shape in REQUIRED_DATASETS.items():
                if rel_path not in demo:
                    result.add_issue("error", f"{demo_path}/{rel_path}", "missing required dataset")
                    continue

                dataset = demo[rel_path]
                shape = tuple(dataset.shape)
                dtype = str(dataset.dtype)
                result.datasets[f"{demo_path}/{rel_path}"] = {
                    "shape": list(shape),
                    "dtype": dtype,
                }
                if shape[0] != num_samples:
                    result.add_issue(
                        "error",
                        f"{demo_path}/{rel_path}",
                        f"first dimension {shape[0]} does not match num_samples {num_samples}",
                    )
                if shape[1:] != trailing_shape:
                    result.add_issue(
                        "error",
                        f"{demo_path}/{rel_path}",
                        f"trailing shape {shape[1:]} does not match expected {trailing_shape}",
                    )

                data = dataset[()]
                _check_finite(result, f"{demo_path}/{rel_path}", data)
                if rel_path.startswith("obs/") and rel_path in {"obs/top", "obs/left_wrist", "obs/right_wrist"}:
                    _check_image(result, f"{demo_path}/{rel_path}", data)
                if rel_path in {"actions", "processed_actions", "obs/actions"}:
                    _check_gripper_symmetry(result, f"{demo_path}/{rel_path}", data, gripper_tolerance)

    return result


def render_markdown_report(result: DatasetValidationResult) -> str:
    status = "PASS" if result.passed else "FAIL"
    lines = [
        "# HDF5 Dataset Validation Report",
        "",
        f"- Status: `{status}`",
        f"- Dataset: `{result.path}`",
        f"- Demos: `{len(result.demos)}`",
        f"- Total samples: `{result.total_samples}`",
        "",
        "## Datasets",
        "",
        "| Path | Shape | Dtype |",
        "|---|---:|---|",
    ]
    for path, meta in sorted(result.datasets.items()):
        lines.append(f"| `{path}` | `{meta['shape']}` | `{meta['dtype']}` |")

    lines.extend(["", "## Issues", ""])
    if not result.issues:
        lines.append("No issues.")
    else:
        lines.extend(["| Level | Path | Message |", "|---|---|---|"])
        for issue in result.issues:
            lines.append(f"| `{issue.level}` | `{issue.path}` | {issue.message} |")
    lines.append("")
    return "\n".join(lines)
