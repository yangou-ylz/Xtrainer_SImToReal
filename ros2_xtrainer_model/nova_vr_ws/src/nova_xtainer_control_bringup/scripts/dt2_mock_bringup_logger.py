#!/usr/bin/env python3
from __future__ import annotations

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node

from nova_vr_common.project_logging import ProjectLogger, create_log_session


class DT2MockBringupLogger(Node):
    def __init__(self) -> None:
        super().__init__("dt2_mock_bringup_logger")
        self.declare_parameter("session_name", "session_dt2_mock_control")
        session_name = self.get_parameter("session_name").value
        session = create_log_session(session_name=session_name)
        self.project_logger = ProjectLogger(self.get_logger(), session)

        self.project_logger.info("bringup", f"DT-2 mock control launch started: session={session.session_dir}")
        self.project_logger.info(
            "bringup",
            "Expected controllers: joint_state_broadcaster, xtrainer_arm_controller, xtrainer_gripper_controller",
        )
        self.project_logger.info(
            "safety",
            "DT-2 uses mock_components/GenericSystem only; no Quest input, Gazebo, MoveIt, or xtrainer SDK real backend is active.",
        )


def main() -> None:
    rclpy.init()
    node = DT2MockBringupLogger()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
