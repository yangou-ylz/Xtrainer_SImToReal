#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import time

import rclpy
from rclpy.duration import Duration
from rclpy.node import Node
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint

from nova_vr_common.project_logging import ProjectLogger, create_log_session


ACTION14_NAMES = [
    "left_joint1", "left_joint2", "left_joint3", "left_joint4", "left_joint5", "left_joint6", "left_gripper",
    "right_joint1", "right_joint2", "right_joint3", "right_joint4", "right_joint5", "right_joint6", "right_gripper",
]

FULL_USD_JOINTS = [
    "J1_1", "J1_2", "J1_3", "J1_4", "J1_5", "J1_6", "J1_7", "J1_8",
    "J2_1", "J2_2", "J2_3", "J2_4", "J2_5", "J2_6", "J2_7", "J2_8",
]

DEFAULT_ACTION14 = [
    0.0, 0.0, -1.20, 0.0, -1.20, 0.0, 0.0,
    0.0, 0.0, 1.20, 0.0, 1.20, 0.0, 0.0,
]


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def action14_to_usd16(values: list[float]) -> list[float]:
    if len(values) != 14:
        raise ValueError("expected 14 action values")
    left = [clamp(float(v), -math.pi, math.pi) for v in values[0:6]]
    left_g = clamp(float(values[6]), 0.0, 1.0)
    right = [clamp(float(v), -math.pi, math.pi) for v in values[7:13]]
    right_g = clamp(float(values[13]), 0.0, 1.0)
    # X-Trainer USD finger joints are at 0.0 when open and move toward
    # +/-0.04 m when closing. Keep the project-level semantic as 0=open,
    # 1=closed.
    left_gripper = [-0.04 * left_g, 0.04 * left_g]
    right_gripper = [-0.04 * right_g, 0.04 * right_g]
    return left + left_gripper + right + right_gripper


class FullCommand14Publisher(Node):
    def __init__(self, session_name: str, topic: str = "/xtrainer_full_joint_controller/joint_trajectory") -> None:
        super().__init__("xtrainer_full_command14")
        self.publisher = self.create_publisher(JointTrajectory, topic, 10)
        self.session = create_log_session(session_name=session_name)
        self.project_logger = ProjectLogger(self.get_logger(), self.session)
        self.topic = topic

    def publish_action14(self, values: list[float], duration: float = 0.8) -> None:
        usd16 = action14_to_usd16(values)
        msg = JointTrajectory()
        msg.joint_names = FULL_USD_JOINTS
        point = JointTrajectoryPoint()
        point.positions = usd16
        point.time_from_start = Duration(seconds=float(duration)).to_msg()
        msg.points.append(point)
        self.publisher.publish(msg)
        self.project_logger.info("adapter", f"full_control action14={values} usd16={usd16} duration={duration:.3f}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send one 14-action command to the full X-Trainer control model.")
    parser.add_argument("--session-name", default="session_full_command14")
    parser.add_argument("--duration", type=float, default=0.8)
    parser.add_argument("--repeat-sec", type=float, default=1.0)
    parser.add_argument("--command14", nargs=14, type=float, default=DEFAULT_ACTION14)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rclpy.init()
    node = FullCommand14Publisher(args.session_name)
    try:
        deadline = time.time() + max(0.1, args.repeat_sec)
        while time.time() < deadline:
            node.publish_action14([float(v) for v in args.command14], duration=args.duration)
            rclpy.spin_once(node, timeout_sec=0.05)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
