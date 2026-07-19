from pathlib import Path

from nova_vr_common.project_logging import create_log_session, file_logger


def test_create_log_session(tmp_path: Path):
    session = create_log_session(workspace=tmp_path, session_name="session_test")
    assert session.session_dir == tmp_path / "logs" / "session_test"
    assert session.bringup_log.exists()
    assert session.adapter_log.exists()
    assert session.safety_log.exists()


def test_file_logger_writes(tmp_path: Path):
    log_path = tmp_path / "test.log"
    logger = file_logger("nova_vr.test_file_logger_writes", log_path)
    logger.info("hello")
    for handler in logger.handlers:
        handler.flush()
    assert "hello" in log_path.read_text(encoding="utf-8")
