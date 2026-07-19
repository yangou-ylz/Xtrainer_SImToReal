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
    parser = argparse.ArgumentParser(description="DT-5 dual-arm position-only IK + gripper mock test.")
    parser.add_argument("--session-name", default="session_dt5_dual_ik")
    parser.add_argument("--duration", type=float, default=1.5)
    parser.add_argument("--left-gripper", type=float, default=0.20)
    parser.add_argument("--right-gripper", type=float, default=0.85)
    return parser.parse_args()


class DT5DualIK(Node):
    def __init__(self, args: argparse.Namespace) -> None:
        super().__init__("dt5_dual_ik_command")
        self.args = args
        self.session = create_log_session(session_name=args.session_name)
        self.project_logger = ProjectLogger(self.get_logger(), self.session)
        self.backend = MockSimBackend(self)
        self.safety = SafetyGate(max_joint_delta=2.0)
        self.joint_state: JointState | None = None
        self.marker_pub = self.create_publisher(Marker, "/xtrainer_control/dual_target_markers", 10)
        self.create_subscription(JointState, "/joint_states", self._on_joint_state, 10)

    def _on_joint_state(self, msg: JointState) -> None:
        self.joint_state = msg

    def _seed(self, side: str) -> np.ndarray:
        if self.joint_state is None:
            return INITIAL_JOINTS[side].copy()
        values = dict(zip(self.joint_state.name, self.joint_state.position))
        out = []
        for index in range(1, 7):
            name = f"{side}_joint{index}"
            if name not in values:
                return INITIAL_JOINTS[side].copy()
            out.append(values[name])
        return np.asarray(out, dtype=float)

    def _publish_marker(self, marker_id: int, target: np.ndarray, color: tuple[float, float, float]) -> None:
        marker = Marker()
        marker.header.frame_id = "xtrainer_control_root"
        marker.header.stamp = self.get_clock().now().to_msg()
        marker.ns = "dt5_dual_targets"
        marker.id = marker_id
        marker.type = Marker.SPHERE
        marker.action = Marker.ADD
        marker.pose.position.x = float(target[0])
        marker.pose.position.y = float(target[1])
        marker.pose.position.z = float(target[2])
        marker.pose.orientation.w = 1.0
        marker.scale.x = marker.scale.y = marker.scale.z = 0.035
        marker.color.r, marker.color.g, marker.color.b = color
        marker.color.a = 0.95
        self.marker_pub.publish(marker)

    def run(self) -> bool:
        deadline = time.time() + 2.0
        while time.time() < deadline and self.joint_state is None:
            rclpy.spin_once(self, timeout_sec=0.05)

        left_seed = self._seed("left")
        right_seed = self._seed("right")
        left_target = tcp_position("left", left_seed) + np.array([-0.030, 0.045, 0.025])
        right_target = tcp_position("right", right_seed) + np.array([0.030, -0.045, 0.025])

        # Simple center exclusion: left target stays left of the platform center, right target stays right.
        if left_target[0] > 0.53 or right_target[0] < 0.53:
            self.project_logger.warn("safety", "DT-5 center exclusion rejected targets")
            return False

        left_result = solve_position_ik("left", left_target, seed=left_seed)
        right_result = solve_position_ik("right", right_target, seed=right_seed)
        self.project_logger.info("adapter", f"DT-5 left target={left_target.round(4).tolist()} result={left_result}")
        self.project_logger.info("adapter", f"DT-5 right target={right_target.round(4).tolist()} result={right_result}")

        if not left_result.success or not right_result.success:
            self.project_logger.warn("safety", "DT-5 IK failed; command not sent")
            return False

        command = parts_to_command14(
            left_result.joints,
            max(0.0, min(1.0, self.args.left_gripper)),
            right_result.joints,
            max(0.0, min(1.0, self.args.right_gripper)),
        )
        safety = self.safety.check(command)
        if not safety.accepted:
            self.project_logger.warn("safety", f"DT-5 safety rejected command: {safety.reason}")
            return False

        deadline = time.time() + 1.0
        while time.time() < deadline:
            self.backend.send(command, duration=self.args.duration)
            self._publish_marker(1, left_target, (0.05, 0.75, 1.0))
            self._publish_marker(2, right_target, (1.0, 0.25, 0.05))
            rclpy.spin_once(self, timeout_sec=0.05)

        self.project_logger.info("bringup", "DT-5 dual-arm IK and gripper command published to mock controller")
        return True


def main() -> None:
    args = parse_args()
    rclpy.init()
    node = DT5DualIK(args)
    try:
        ok = node.run()
    finally:
        node.destroy_node()
        rclpy.shutdown()
    raise SystemExit(0 if ok else 2)


if __name__ == "__main__":
    main()
