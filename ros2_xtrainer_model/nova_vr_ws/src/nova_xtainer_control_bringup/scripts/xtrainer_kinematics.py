from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np


ARM_JOINTS = {
    "left": [f"left_joint{i}" for i in range(1, 7)],
    "right": [f"right_joint{i}" for i in range(1, 7)],
}

ARM_CONTROLLER_JOINTS = ARM_JOINTS["left"] + ARM_JOINTS["right"]
COMMAND14_JOINTS = (
    ARM_JOINTS["left"]
    + ["left_gripper_joint"]
    + ARM_JOINTS["right"]
    + ["right_gripper_joint"]
)

INITIAL_JOINTS = {
    "left": np.array([0.0, 0.0, -1.5708, 0.0, -1.5708, 0.0], dtype=float),
    "right": np.array([0.0, 0.0, 1.5708, 0.0, 1.5708, 0.0], dtype=float),
}

JOINT_LIMITS = np.array(
    [
        [-6.28, 6.28],
        [-3.14, 3.14],
        [-2.79, 2.79],
        [-6.28, 6.28],
        [-6.28, 6.28],
        [-6.28, 6.28],
    ],
    dtype=float,
)

BASE_XYZ = {
    "left": np.array([0.0, -0.016, 0.0], dtype=float),
    "right": np.array([1.06, -0.016, 0.0], dtype=float),
}

JOINT_ORIGINS = [
    ([0.0, 0.0, 0.2234], [0.0, 0.0, 0.0], [0.0, 0.0, -1.0]),
    ([0.0, 0.0, 0.0], [math.pi / 2.0, math.pi / 2.0, 0.0], [0.0, 0.0, 1.0]),
    ([-0.28, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 1.0]),
    ([-0.22501, 0.0, 0.1175], [0.0, 0.0, -math.pi / 2.0], [0.0, 0.0, -1.0]),
    ([0.0, -0.12, 0.0], [math.pi / 2.0, 0.0, 0.0], [0.0, 0.0, -1.0]),
    ([0.0, 0.088004, 0.0], [-math.pi / 2.0, 0.0, 0.0], [0.0, 0.0, 1.0]),
]

TCP_OFFSET = np.array([0.18, 0.0, -0.025], dtype=float)


@dataclass
class IKResult:
    success: bool
    joints: np.ndarray
    position: np.ndarray
    error_norm: float
    iterations: int
    reason: str


def rpy_matrix(rpy: np.ndarray | list[float]) -> np.ndarray:
    roll, pitch, yaw = [float(v) for v in rpy]
    cr, sr = math.cos(roll), math.sin(roll)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)
    rx = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]], dtype=float)
    ry = np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]], dtype=float)
    rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]], dtype=float)
    return rz @ ry @ rx


def axis_angle_matrix(axis: np.ndarray | list[float], angle: float) -> np.ndarray:
    axis = np.asarray(axis, dtype=float)
    axis = axis / np.linalg.norm(axis)
    x, y, z = axis
    c, s = math.cos(angle), math.sin(angle)
    cc = 1.0 - c
    return np.array(
        [
            [c + x * x * cc, x * y * cc - z * s, x * z * cc + y * s],
            [y * x * cc + z * s, c + y * y * cc, y * z * cc - x * s],
            [z * x * cc - y * s, z * y * cc + x * s, c + z * z * cc],
        ],
        dtype=float,
    )


def transform(xyz: np.ndarray | list[float], rpy: np.ndarray | list[float]) -> np.ndarray:
    out = np.eye(4, dtype=float)
    out[:3, :3] = rpy_matrix(rpy)
    out[:3, 3] = np.asarray(xyz, dtype=float)
    return out


def rotate(axis: np.ndarray | list[float], angle: float) -> np.ndarray:
    out = np.eye(4, dtype=float)
    out[:3, :3] = axis_angle_matrix(axis, angle)
    return out


def translate(xyz: np.ndarray | list[float]) -> np.ndarray:
    out = np.eye(4, dtype=float)
    out[:3, 3] = np.asarray(xyz, dtype=float)
    return out


def fk_matrix(side: str, joints: np.ndarray | list[float]) -> np.ndarray:
    q = np.asarray(joints, dtype=float)
    t = transform(BASE_XYZ[side], [0.0, 0.0, 0.0])
    for value, (xyz, rpy, axis) in zip(q, JOINT_ORIGINS):
        t = t @ transform(xyz, rpy) @ rotate(axis, float(value))
    return t @ translate(TCP_OFFSET)


def tcp_position(side: str, joints: np.ndarray | list[float]) -> np.ndarray:
    return fk_matrix(side, joints)[:3, 3]


def numerical_jacobian(side: str, joints: np.ndarray, eps: float = 1e-4) -> np.ndarray:
    base = tcp_position(side, joints)
    jac = np.zeros((3, 6), dtype=float)
    for index in range(6):
        shifted = joints.copy()
        shifted[index] += eps
        jac[:, index] = (tcp_position(side, shifted) - base) / eps
    return jac


def clamp_joints(joints: np.ndarray) -> np.ndarray:
    return np.clip(joints, JOINT_LIMITS[:, 0], JOINT_LIMITS[:, 1])


def solve_position_ik(
    side: str,
    target: np.ndarray | list[float],
    seed: np.ndarray | list[float] | None = None,
    tolerance: float = 0.012,
    max_iterations: int = 140,
    damping: float = 0.06,
    max_step: float = 0.10,
) -> IKResult:
    q = np.array(seed if seed is not None else INITIAL_JOINTS[side], dtype=float)
    q = clamp_joints(q)
    target = np.asarray(target, dtype=float)
    reason = "max_iterations"

    for iteration in range(1, max_iterations + 1):
        pos = tcp_position(side, q)
        error = target - pos
        norm = float(np.linalg.norm(error))
        if norm <= tolerance:
            return IKResult(True, q, pos, norm, iteration, "converged")

        jac = numerical_jacobian(side, q)
        lhs = jac @ jac.T + (damping * damping) * np.eye(3)
        try:
            dq = jac.T @ np.linalg.solve(lhs, error)
        except np.linalg.LinAlgError:
            reason = "singular_jacobian"
            break

        step_norm = float(np.linalg.norm(dq))
        if step_norm > max_step:
            dq *= max_step / step_norm
        q = clamp_joints(q + dq)

    pos = tcp_position(side, q)
    error_norm = float(np.linalg.norm(target - pos))
    return IKResult(error_norm <= tolerance, q, pos, error_norm, max_iterations, reason)


def command14_to_parts(values: list[float]) -> tuple[np.ndarray, float, np.ndarray, float]:
    if len(values) != 14:
        raise ValueError(f"XTrainerCommand14 requires 14 values, got {len(values)}")
    left = np.asarray(values[0:6], dtype=float)
    left_gripper = float(values[6])
    right = np.asarray(values[7:13], dtype=float)
    right_gripper = float(values[13])
    return left, left_gripper, right, right_gripper


def parts_to_command14(
    left: np.ndarray | list[float],
    left_gripper: float,
    right: np.ndarray | list[float],
    right_gripper: float,
) -> list[float]:
    return (
        [float(v) for v in left]
        + [float(left_gripper)]
        + [float(v) for v in right]
        + [float(right_gripper)]
    )
