import logging
from logging.handlers import RotatingFileHandler

from app.core.config import Settings
from app.core.logging import configure_logging


def test_configure_logging_adds_bounded_file_handler(tmp_path) -> None:
    log_path = tmp_path / "backend.log"
    settings = Settings(
        _env_file=None,
        log_file_path=str(log_path),
        log_max_bytes=1024,
        log_backup_count=2,
    )

    configure_logging(settings)

    handlers = [
        handler
        for handler in logging.getLogger().handlers
        if isinstance(handler, RotatingFileHandler)
        and handler.baseFilename == str(log_path)
    ]
    assert handlers
    assert handlers[0].maxBytes == 1024
    assert handlers[0].backupCount == 2
