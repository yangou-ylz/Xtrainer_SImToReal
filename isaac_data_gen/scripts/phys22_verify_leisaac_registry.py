#!/usr/bin/env python3
"""Verify LeIsaac task registration after bootstrapping Isaac Sim."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from phys_data_gen.logging_utils import log_environment, mark_pass, setup_logging


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-name", default=None)
    args = parser.parse_args()

    session = setup_logging(session_name=args.session_name)
    session.run.info("phys22_verify_leisaac_registry_start")
    log_environment(session, extra={"stage": "PHYS-2.2"})

    from isaaclab.app import AppLauncher

    app_launcher = AppLauncher(headless=True)
    simulation_app = app_launcher.app

    try:
        import gymnasium as gym
        import leisaac
        import leisaac.tasks  # noqa: F401

        task_id = "LeIsaac-XTrainer-PickCube-v0"
        task_ids = sorted(task_spec.id for task_spec in gym.registry.values() if "LeIsaac" in task_spec.id)
        session.data.info("leisaac_module=%s", getattr(leisaac, "__file__", ""))
        session.data.info("leisaac_tasks=%s", task_ids)
        if task_id not in task_ids:
            session.run.error("task_not_registered task=%s", task_id)
            return 3

        required_assets = [
            ROOT / "external/x-trainer/assets/robots/x_trainer.usd",
            ROOT / "external/x-trainer/assets/scenes/table_with_cube/scene.usd",
            ROOT / "external/x-trainer/assets/scenes/table_with_cube/cube/cube.usd",
            ROOT / "external/x-trainer/assets/scenes/table_with_cube/Plate/Plate.usd",
        ]
        for asset in required_assets:
            if not asset.is_file() or asset.stat().st_size == 0:
                session.run.error("missing_asset=%s", asset)
                return 4
            session.data.info("asset_ok path=%s size=%d", asset, asset.stat().st_size)

        mark_pass(session, "PASS_PHYS22_LEISAAC_REGISTRY", "LeIsaac registry verified")
        session.run.info("phys22_verify_leisaac_registry_ok")
        return 0
    finally:
        try:
            simulation_app.close(wait_for_replicator=False, skip_cleanup=True)
        except TypeError:
            simulation_app.close()


if __name__ == "__main__":
    raise SystemExit(main())
