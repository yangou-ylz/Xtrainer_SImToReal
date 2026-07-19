from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
from rclpy.duration import Duration
from std_msgs.msg import Float64MultiArray
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint

from xtrainer_kinematics import (
    ARM_CONTROLLER_JOINTS,
    COMMAND14_JOINTS,
    JOINT_LIMITS,
    command14_to_parts,
)


@dataclass
class SafetyResult:
    accepted: bool
    values: list[float]
    reason: str


class Backend(Protocol):
    name: str

    def send(self, values: list[float], duration: float = 1.0) -> None:
        ...


class SafetyGate:
    def __init__(self, max_joint_delta: float = 0.35) -> None:
        self.max_joint_delta = max_joint_delta
        self._previous: np.ndarray | None = None

    def check(self, values: list[float]) -> SafetyResult:
        try:
            left, left_gripper, right, right_gripper = command14_to_parts(values)
        except ValueError as exc:
            return SafetyResult(False, values, str(exc))

        if not (0.0 <= left_gripper <= 1.0 and 0.0 <= right_gripper <= 1.0):
            return SafetyResult(False, values, "gripper values must be in [0, 1]")

        for side_name, joints in (("left", left), ("right", right)):
            below = joints < JOINT_LIMITS[:, 0]
            above = joints > JOINT_LIMITS[:, 1]
            if bool(np.any(below | above)):
                return SafetyResult(False, values, f"{side_name} joint target outside configured limits")

        current = np.asarray(values, dtype=float)
        if self._previous is not None:
            delta = np.abs(current - self._previous)
            # Ignore gripper delta for the arm jump limit.
            arm_delta = np.r_[delta[0:6], delta[7:13]]
            if float(np.max(arm_delta)) > self.max_joint_delta:
                return SafetyResult(False, values, "joint delta clamp triggered")

        self._previous = current
        return SafetyResult(True, values, "accepted")


class MockSimBackend:
    name = "mock_sim"

    def __init__(self, node, arm_topic: str = "/xtrainer_arm_controller/joint_trajectory", gripper_topic: str = "/xtrainer_gripper_controller/commands") -> None:
        self.node = node
        self.arm_pub = node.create_publisher(JointTrajectory, arm_topic, 10)
        self.gripper_pub = node.create_publisher(Float64MultiArray, gripper_topic, 10)

    def send(self, values: list[float], duration: float = 1.0) -> None:
        left, left_gripper, right, right_gripper = command14_to_parts(values)

        trajectory = JointTrajectory()
        trajectory.joint_names = ARM_CONTROLLER_JOINTS
        point = JointTrajectoryPoint()
        point.positions = [float(v) for v in np.r_[left, right]]
        point.time_from_start = Duration(seconds=float(duration)).to_msg()
        trajectory.points.append(point)

        grippers = Float64MultiArray()
        grippers.data = [float(left_gripper), float(right_gripper)]

        self.arm_pub.publish(trajectory)
        self.gripper_pub.publish(grippers)


class GazeboSimBackend(MockSimBackend):
    name = "gazebo_sim"


class XTrainerDryRunBackend:
    name = "xtrainer_dry_run"

    def __init__(self, logger) -> None:
        self.logger = logger

    def send(self, values: list[float], duration: float = 1.0) -> None:
        left, left_gripper, right, right_gripper = command14_to_parts(values)
        left_deg = np.rad2deg(left).round(3).tolist()
        right_deg = np.rad2deg(right).round(3).tolist()
        left_gripper_u8 = int(round(np.clip(left_gripper, 0.0, 1.0) * 255.0))
        right_gripper_u8 = int(round(np.clip(right_gripper, 0.0, 1.0) * 255.0))
        self.logger.info(
            "adapter",
            "xtrainer_dry_run command "
            f"joints={COMMAND14_JOINTS} left_deg={left_deg} left_gripper_u8={left_gripper_u8} "
            f"right_deg={right_deg} right_gripper_u8={right_gripper_u8} duration={duration:.3f}",
        )
