from __future__ import annotations

import rclpy
from rclpy.node import Node

from nova_vr_common.project_logging import ProjectLogger, create_log_session


class LoggingSmokeTest(Node):
    def __init__(self) -> None:
        super().__init__("nova_vr_logging_smoke_test")
        self.declare_parameter("session_name", "")
        session_name = self.get_parameter("session_name").value or None
        self.session = create_log_session(session_name=session_name)
        self.project_logger = ProjectLogger(self.get_logger(), self.session)

        self.project_logger.info(
            "bringup",
            f"logging smoke test started session_dir={self.session.session_dir}",
        )
        self.project_logger.info("adapter", "adapter log channel ready")
        self.project_logger.warn("safety", "safety log channel ready")
        self.project_logger.error("safety", "example error event for log verification")
        self.project_logger.info("bringup", "logging smoke test completed")


def main() -> None:
    rclpy.init()
    node = LoggingSmokeTest()
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
