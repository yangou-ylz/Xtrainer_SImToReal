#!/usr/bin/env python3
from __future__ import annotations

import argparse
import time

import rclpy
from rclpy.node import Node

from nova_vr_common.project_logging import ProjectLogger, create_log_session
from xtrainer_backend import GazeboSimBackend, MockSimBackend, SafetyGate, XTrainerDryRunBackend


DEFAULT_COMMAND14 = [
    0.05,
    -0.15,
    -1.35,
    0.05,
    -1.35,
    0.05,
    0.30,
    -0.05,
    -0.15,
    1.35,
    -0.05,
    1.35,
    -0.05,
    0.80,
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DT-7 unified XTrainerCommand14 backend test.")
    parser.add_argument("--session-name", default="session_dt7_command14")
    parser.add_argument("--backend", choices=["mock_sim", "gazebo_sim", "xtrainer_dry_run"], default="mock_sim")
    parser.add_argument("--duration", type=float, default=1.5)
    parser.add_argument("--command14", nargs=14, type=float, default=DEFAULT_COMMAND14)
    return parser.parse_args()


class DT7Command14(Node):
    def __init__(self, args: argparse.Namespace) -> None:
        super().__init__("dt7_command14_backend")
        self.args = args
        self.session = create_log_session(session_name=args.session_name)
        self.project_logger = ProjectLogger(self.get_logger(), self.session)
        self.safety = SafetyGate(max_joint_delta=10.0)
        if args.backend == "mock_sim":
            self.backend = MockSimBackend(self)
        elif args.backend == "gazebo_sim":
            self.backend = GazeboSimBackend(self)
        else:
            self.backend = XTrainerDryRunBackend(self.project_logger)

    def run(self) -> bool:
        values = [float(v) for v in self.args.command14]
        safety = self.safety.check(values)
        self.project_logger.info("adapter", f"DT-7 backend={self.backend.name} command14={values}")
        if not safety.accepted:
            self.project_logger.warn("safety", f"DT-7 safety rejected command: {safety.reason}")
            return False

        deadline = time.time() + 1.0
        while time.time() < deadline:
            self.backend.send(values, duration=self.args.duration)
            rclpy.spin_once(self, timeout_sec=0.05)
        self.project_logger.info("bringup", f"DT-7 command accepted by backend={self.backend.name}")
        return True


def main() -> None:
    args = parse_args()
    rclpy.init()
    node = DT7Command14(args)
    try:
        ok = node.run()
    finally:
        node.destroy_node()
        rclpy.shutdown()
    raise SystemExit(0 if ok else 2)


if __name__ == "__main__":
    main()
