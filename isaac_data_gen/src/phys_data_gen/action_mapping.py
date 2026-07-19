"""Action mapping between project XTrainerCommand14 and LeIsaac 16-DoF actions."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


COMMAND14_SIZE = 14
LEISAAC16_SIZE = 16
DEFAULT_GRIPPER_WIDTH_M = 0.04

COMMAND14_NAMES = (
    "left_joint1",
    "left_joint2",
    "left_joint3",
    "left_joint4",
    "left_joint5",
    "left_joint6",
    "left_gripper",
    "right_joint1",
    "right_joint2",
    "right_joint3",
    "right_joint4",
    "right_joint5",
    "right_joint6",
    "right_gripper",
)

LEISAAC16_NAMES = (
    "J1_1.pos",
    "J1_2.pos",
    "J1_3.pos",
    "J1_4.pos",
    "J1_5.pos",
    "J1_6.pos",
    "J1_7.pos",
    "J1_8.pos",
    "J2_1.pos",
    "J2_2.pos",
    "J2_3.pos",
    "J2_4.pos",
    "J2_5.pos",
    "J2_6.pos",
    "J2_7.pos",
    "J2_8.pos",
)


@dataclass(frozen=True)
class GripperSymmetry:
    left_max_abs: float
    right_max_abs: float
    tolerance: float

    @property
    def passed(self) -> bool:
        return self.left_max_abs <= self.tolerance and self.right_max_abs <= self.tolerance


def _as_last_dim_array(values, expected_size: int, name: str) -> np.ndarray:
    array = np.asarray(values, dtype=np.float32)
    if array.shape == ():
        raise ValueError(f"{name} must have last dimension {expected_size}, got scalar")
    if array.shape[-1] != expected_size:
        raise ValueError(f"{name} must have last dimension {expected_size}, got shape {array.shape}")
    return array


def command14_to_leisaac16(
    command14,
    *,
    gripper_width_m: float = DEFAULT_GRIPPER_WIDTH_M,
    clamp_gripper: bool = True,
) -> np.ndarray:
    """Map project 14-D command(s) to LeIsaac 16-D follower action(s)."""

    command = _as_last_dim_array(command14, COMMAND14_SIZE, "command14")
    mapped = np.zeros(command.shape[:-1] + (LEISAAC16_SIZE,), dtype=np.float32)

    mapped[..., 0:6] = command[..., 0:6]
    mapped[..., 8:14] = command[..., 7:13]

    left_u = command[..., 6]
    right_u = command[..., 13]
    if clamp_gripper:
        left_u = np.clip(left_u, 0.0, 1.0)
        right_u = np.clip(right_u, 0.0, 1.0)

    mapped[..., 7] = left_u * gripper_width_m
    mapped[..., 6] = -mapped[..., 7]
    mapped[..., 15] = right_u * gripper_width_m
    mapped[..., 14] = -mapped[..., 15]
    return mapped


def leisaac16_to_command14(
    leisaac16,
    *,
    gripper_width_m: float = DEFAULT_GRIPPER_WIDTH_M,
    clamp_gripper: bool = True,
) -> np.ndarray:
    """Map LeIsaac 16-D action/state(s) back to project 14-D command semantic(s)."""

    action = _as_last_dim_array(leisaac16, LEISAAC16_SIZE, "leisaac16")
    command = np.zeros(action.shape[:-1] + (COMMAND14_SIZE,), dtype=np.float32)
    command[..., 0:6] = action[..., 0:6]
    command[..., 7:13] = action[..., 8:14]
    command[..., 6] = action[..., 7] / gripper_width_m
    command[..., 13] = action[..., 15] / gripper_width_m
    if clamp_gripper:
        command[..., 6] = np.clip(command[..., 6], 0.0, 1.0)
        command[..., 13] = np.clip(command[..., 13], 0.0, 1.0)
    return command


def check_leisaac16_gripper_symmetry(leisaac16, *, tolerance: float = 1e-5) -> GripperSymmetry:
    """Check `J*_7 = -J*_8` for LeIsaac gripper pairs."""

    action = _as_last_dim_array(leisaac16, LEISAAC16_SIZE, "leisaac16")
    left = np.max(np.abs(action[..., 6] + action[..., 7])).item()
    right = np.max(np.abs(action[..., 14] + action[..., 15])).item()
    return GripperSymmetry(left_max_abs=float(left), right_max_abs=float(right), tolerance=float(tolerance))


def make_replay_command14(
    *,
    left_j1: float = 0.08,
    right_j1: float = -0.08,
    left_gripper: float = 0.25,
    right_gripper: float = 0.25,
) -> np.ndarray:
    """Small deterministic command used by smoke tests."""

    command = np.zeros((COMMAND14_SIZE,), dtype=np.float32)
    command[0] = left_j1
    command[6] = left_gripper
    command[7] = right_j1
    command[13] = right_gripper
    return command
