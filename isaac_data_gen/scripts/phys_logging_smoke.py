#!/usr/bin/env python3
"""Smoke test for the project logging utility."""

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
    parser.add_argument("--session-name", default="session_logging_smoke")
    args = parser.parse_args()

    session = setup_logging(session_name=args.session_name)
    session.run.info("logging_smoke_start")
    log_environment(session, extra={"smoke": True})
    session.data.info("sample_data_event frames=%d action_dim=%d", 0, 16)
    mark_pass(session, "PASS_LOGGING_SMOKE", "logging smoke passed")

    required = [session.run_log, session.env_log, session.data_log, session.error_log, session.root / "PASS_LOGGING_SMOKE"]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        session.run.error("missing_outputs=%s", missing)
        return 1
    session.run.info("logging_smoke_ok root=%s", session.root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
