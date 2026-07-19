"""Project-wide logging helpers for simulation data generation scripts."""

from __future__ import annotations

import logging
import os
import platform
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Mapping


LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


@dataclass(frozen=True)
class LogSession:
    """Paths and named loggers for one run."""

    root: Path
    run_log: Path
    env_log: Path
    data_log: Path
    error_log: Path
    run: logging.Logger
    env: logging.Logger
    data: logging.Logger


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def make_session_dir(
    session_name: str | None = None,
    logs_root: str | Path | None = None,
) -> Path:
    logs_dir = Path(logs_root) if logs_root is not None else project_root() / "logs"
    if session_name is None:
        session_name = "session_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    session_dir = logs_dir / session_name
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def _reset_logger(logger: logging.Logger) -> None:
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.DEBUG)


def _file_handler(path: Path, level: int = logging.DEBUG) -> logging.Handler:
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    return handler


def _console_handler(level: int = logging.INFO) -> logging.Handler:
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter("%(levelname)s | %(name)s | %(message)s"))
    return handler


def _build_logger(name: str, file_path: Path, error_path: Path, console: bool) -> logging.Logger:
    logger = logging.getLogger(name)
    _reset_logger(logger)
    logger.addHandler(_file_handler(file_path))
    logger.addHandler(_file_handler(error_path, logging.ERROR))
    if console:
        logger.addHandler(_console_handler())
    return logger


def setup_logging(
    session_name: str | None = None,
    logs_root: str | Path | None = None,
    console: bool = True,
) -> LogSession:
    """Create one logging session with run/env/data/error logs."""

    session_dir = make_session_dir(session_name=session_name, logs_root=logs_root)
    run_log = session_dir / "run.log"
    env_log = session_dir / "env.log"
    data_log = session_dir / "data.log"
    error_log = session_dir / "error.log"

    run_logger = _build_logger("phys.run", run_log, error_log, console)
    env_logger = _build_logger("phys.env", env_log, error_log, console)
    data_logger = _build_logger("phys.data", data_log, error_log, console)

    run_logger.info("log_session_start root=%s", session_dir)
    return LogSession(
        root=session_dir,
        run_log=run_log,
        env_log=env_log,
        data_log=data_log,
        error_log=error_log,
        run=run_logger,
        env=env_logger,
        data=data_logger,
    )


def _run_text(command: list[str], timeout_sec: int = 5) -> str:
    try:
        completed = subprocess.run(
            command,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout_sec,
        )
        return completed.stdout.strip()
    except Exception as exc:  # pragma: no cover - diagnostic best effort
        return f"unavailable: {exc}"


def log_environment(session: LogSession, extra: Mapping[str, object] | None = None) -> None:
    """Record reproducibility-critical environment facts."""

    session.env.info("cwd=%s", Path.cwd())
    session.env.info("python=%s", sys.executable)
    session.env.info("python_version=%s", sys.version.replace("\n", " "))
    session.env.info("platform=%s", platform.platform())
    session.env.info("conda_default_env=%s", os.environ.get("CONDA_DEFAULT_ENV", ""))
    session.env.info("cuda_visible_devices=%s", os.environ.get("CUDA_VISIBLE_DEVICES", ""))
    session.env.info("nvidia_smi=%s", _run_text(["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"]))
    session.env.info("git_head=%s", _run_text(["git", "rev-parse", "HEAD"]))
    if extra:
        for key, value in extra.items():
            session.env.info("%s=%s", key, value)


def mark_pass(session: LogSession, marker_name: str, message: str = "pass") -> Path:
    marker = session.root / marker_name
    marker.write_text(message + "\n", encoding="utf-8")
    session.run.info("pass_marker=%s", marker)
    return marker


def mark_fail(session: LogSession, marker_name: str, message: str) -> Path:
    marker = session.root / marker_name
    marker.write_text(message + "\n", encoding="utf-8")
    session.run.error("fail_marker=%s reason=%s", marker, message)
    return marker

