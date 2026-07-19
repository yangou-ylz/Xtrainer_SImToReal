#!/usr/bin/env python3
from __future__ import annotations

import argparse
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import Float64MultiArray
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint

from nova_vr_common.project_logging import ProjectLogger, create_log_session


ARM_JOINTS = [
    "left_joint1",
    "left_joint2",
    "left_joint3",
    "left_joint4",
    "left_joint5",
    "left_joint6",
    "right_joint1",
    "right_joint2",
    "right_joint3",
    "right_joint4",
    "right_joint5",
    "right_joint6",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send a DT-2 mock XTrainerCommand14 test command.")
    parser.add_argument("--session-name", default="session_dt2_mock_command")
    parser.add_argument("--duration", type=float, default=2.0)
    parser.add_argument(
        "--arms",
        nargs=12,
        type=float,
        default=[0.20, -0.35, 0.25, 0.15, 0.30, -0.20, -0.20, -0.35, 0.25, -0.15, 0.30, 0.20],
        metavar="RAD",
        help="12 arm joint targets in rad: left_joint1..6 then right_joint1..6.",
    )
    parser.add_argument(
        "--grippers",
        nargs=2,
        type=float,
        default=[0.75, 0.75],
        metavar="NORM",
        help="left/right gripper targets in normalized 0..1 semantic.",
    )
    return parser.parse_args()


class DT2MockCommandSender(Node):
    def __init__(self, args: argparse.Namespace) -> None:
        super().__init__("send_dt2_mock_command")
        self.args = args
        session = create_log_session(session_name=args.session_name)
        self.project_logger = ProjectLogger(self.get_logger(), session)
        self.arm_pub = self.create_publisher(JointTrajectory, "/xtrainer_arm_controller/joint_trajectory", 10)
        self.gripper_pub = self.create_publisher(Float64MultiArray, "/xtrainer_gripper_controller/commands", 10)

    def send(self) -> None:
        arms = list(self.args.arms)
        grippers = [max(0.0, min(1.0, value)) for value in self.args.grippers]

        self.project_logger.info("bringup", f"Sending DT-2 arm mock target rad={arms}")
        self.project_logger.info("safety", f"Sending DT-2 gripper normalized target={grippers}")

        trajectory = JointTrajectory()
        trajectory.joint_names = ARM_JOINTS
        point = JointTrajectoryPoint()
        point.positions = arms
        point.time_from_start.sec = int(self.args.duration)
        point.time_from_start.nanosec = int((self.args.duration - int(self.args.duration)) * 1e9)
        trajectory.points.append(point)

        gripper_msg = Float64MultiArray()
        gripper_msg.data = grippers

        deadline = time.time() + 1.0
        while time.time() < deadline:
            self.arm_pub.publish(trajectory)
            self.gripper_pub.publish(gripper_msg)
            rclpy.spin_once(self, timeout_sec=0.05)

        self.project_logger.info("bringup", "DT-2 mock command published.")


def main() -> None:
    args = parse_args()
    rclpy.init()
    node = DT2MockCommandSender(args)
    try:
        node.send()
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
