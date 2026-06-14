import logging
from logging.handlers import RotatingFileHandler

from app.core.config import Settings


def configure_logging(settings: Settings) -> None:
    level = logging.getLevelName(settings.log_level.strip().upper())
    if not isinstance(level, int):
        level = logging.INFO

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    if not root_logger.handlers:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    log_path = settings.log_path
    resolved_log_path = str(log_path)
    for handler in root_logger.handlers:
        if isinstance(handler, RotatingFileHandler) and handler.baseFilename == resolved_log_path:
            handler.setLevel(level)
            return

    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=settings.log_max_bytes,
        backupCount=settings.log_backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
