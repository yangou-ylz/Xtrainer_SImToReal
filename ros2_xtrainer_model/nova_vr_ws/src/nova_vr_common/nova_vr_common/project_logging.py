from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


DEFAULT_WORKSPACE = Path.cwd()
DEFAULT_LOG_NAMES = ("bringup", "adapter", "safety")


@dataclass(frozen=True)
class ProjectLogSession:
    session_dir: Path
    bringup_log: Path
    adapter_log: Path
    safety_log: Path

    def path_for(self, channel: str) -> Path:
        if channel == "bringup":
            return self.bringup_log
        if channel == "adapter":
            return self.adapter_log
        if channel == "safety":
            return self.safety_log
        return self.session_dir / f"{channel}.log"


def default_workspace() -> Path:
    return Path(os.environ.get("NOVA_VR_WS", str(DEFAULT_WORKSPACE))).expanduser()


def create_log_session(
    workspace: Path | None = None,
    session_name: str | None = None,
    log_names: Iterable[str] = DEFAULT_LOG_NAMES,
) -> ProjectLogSession:
    ws = workspace or default_workspace()
    stamp = session_name or datetime.now().strftime("session_%Y%m%d_%H%M%S")
    session_dir = ws / "logs" / stamp
    session_dir.mkdir(parents=True, exist_ok=True)

    paths = {name: session_dir / f"{name}.log" for name in log_names}
    for path in paths.values():
        path.touch(exist_ok=True)

    return ProjectLogSession(
        session_dir=session_dir,
        bringup_log=paths.get("bringup", session_dir / "bringup.log"),
        adapter_log=paths.get("adapter", session_dir / "adapter.log"),
        safety_log=paths.get("safety", session_dir / "safety.log"),
    )


def file_logger(name: str, path: Path, level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    resolved = str(path.resolve())
    for handler in logger.handlers:
        if isinstance(handler, logging.FileHandler) and handler.baseFilename == resolved:
            return logger

    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setLevel(level)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s.%(msecs)03d %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(handler)
    return logger


class ProjectLogger:
    def __init__(self, ros_logger, session: ProjectLogSession):
        self.ros_logger = ros_logger
        self.session = session
        self._file_loggers = {
            "bringup": file_logger("nova_vr.bringup", session.bringup_log),
            "adapter": file_logger("nova_vr.adapter", session.adapter_log),
            "safety": file_logger("nova_vr.safety", session.safety_log),
        }

    def info(self, channel: str, message: str) -> None:
        self.ros_logger.info(message)
        self._file(channel).info(message)

    def warn(self, channel: str, message: str) -> None:
        self.ros_logger.warn(message)
        self._file(channel).warning(message)

    def error(self, channel: str, message: str) -> None:
        self.ros_logger.error(message)
        self._file(channel).error(message)

    def _file(self, channel: str) -> logging.Logger:
        if channel not in self._file_loggers:
            self._file_loggers[channel] = file_logger(
                f"nova_vr.{channel}",
                self.session.path_for(channel),
            )
        return self._file_loggers[channel]
