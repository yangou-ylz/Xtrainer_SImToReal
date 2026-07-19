#!/usr/bin/env python3
from __future__ import annotations

import argparse
import time

import numpy as np
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState
from visualization_msgs.msg import Marker

from nova_vr_common.project_logging import ProjectLogger, create_log_session
from xtrainer_backend import MockSimBackend, SafetyGate
from xtrainer_kinematics import INITIAL_JOINTS, parts_to_command14, solve_position_ik, tcp_position


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DT-4 right-arm position-only IK test.")
    parser.add_argument("--session-name", default="session_dt4_right_ik")
    parser.add_argument("--target", nargs=3, type=float, default=None, metavar=("X", "Y", "Z"))
    parser.add_argument("--duration", type=float, default=1.5)
    return parser.parse_args()


class DT4RightIK(Node):
    def __init__(self, args: argparse.Namespace) -> None:
        super().__init__("dt4_right_ik_target")
        self.args = args
        self.session = create_log_session(session_name=args.session_name)
        self.project_logger = ProjectLogger(self.get_logger(), self.session)
        self.backend = MockSimBackend(self)
        self.safety = SafetyGate(max_joint_delta=2.0)
        self.joint_state: JointState | None = None
        self.marker_pub = self.create_publisher(Marker, "/xtrainer_control/right_target_marker", 10)
        self.create_subscription(JointState, "/joint_states", self._on_joint_state, 10)

    def _on_joint_state(self, msg: JointState) -> None:
        self.joint_state = msg

    def _current_right_seed(self) -> np.ndarray:
        if self.joint_state is None:
            return INITIAL_JOINTS["right"].copy()
        values = dict(zip(self.joint_state.name, self.joint_state.position))
        joints = []
        for index in range(1, 7):
            name = f"right_joint{index}"
            if name not in values:
                return INITIAL_JOINTS["right"].copy()
            joints.append(values[name])
        return np.asarray(joints, dtype=float)

    def _publish_marker(self, target: np.ndarray) -> None:
        marker = Marker()
        marker.header.frame_id = "xtrainer_control_root"
        marker.header.stamp = self.get_clock().now().to_msg()
        marker.ns = "dt4_right_target"
        marker.id = 1
        marker.type = Marker.SPHERE
        marker.action = Marker.ADD
        marker.pose.position.x = float(target[0])
        marker.pose.position.y = float(target[1])
        marker.pose.position.z = float(target[2])
        marker.pose.orientation.w = 1.0
        marker.scale.x = 0.035
        marker.scale.y = 0.035
        marker.scale.z = 0.035
        marker.color.r = 1.0
        marker.color.g = 0.25
        marker.color.b = 0.05
        marker.color.a = 0.95
        self.marker_pub.publish(marker)

    def run(self) -> bool:
        deadline = time.time() + 2.0
        while time.time() < deadline and self.joint_state is None:
            rclpy.spin_once(self, timeout_sec=0.05)

        seed = self._current_right_seed()
        current = tcp_position("right", seed)
        target = np.asarray(self.args.target, dtype=float) if self.args.target else current + np.array([0.035, -0.035, 0.025])
        self._publish_marker(target)

        result = solve_position_ik("right", target, seed=seed)
        self.project_logger.info("adapter", f"DT-4 target={target.round(4).tolist()} seed={seed.round(4).tolist()}")
        self.project_logger.info(
            "adapter",
            f"DT-4 IK success={result.success} reason={result.reason} error={result.error_norm:.5f} "
            f"iterations={result.iterations} joints={result.joints.round(4).tolist()}",
        )
        if not result.success:
            self.project_logger.warn("safety", "DT-4 IK failed; command not sent")
            return False

        left = INITIAL_JOINTS["left"].copy()
        command = parts_to_command14(left, 0.75, result.joints, 0.75)
        safety = self.safety.check(command)
        if not safety.accepted:
            self.project_logger.warn("safety", f"DT-4 safety rejected command: {safety.reason}")
            return False

        deadline = time.time() + 1.0
        while time.time() < deadline:
            self.backend.send(command, duration=self.args.duration)
            self._publish_marker(target)
            rclpy.spin_once(self, timeout_sec=0.05)
        self.project_logger.info("bringup", "DT-4 right-arm IK command published to mock controller")
        return True


def main() -> None:
    args = parse_args()
    rclpy.init()
    node = DT4RightIK(args)
    try:
        ok = node.run()
    finally:
        node.destroy_node()
        rclpy.shutdown()
    raise SystemExit(0 if ok else 2)


if __name__ == "__main__":
    main()
