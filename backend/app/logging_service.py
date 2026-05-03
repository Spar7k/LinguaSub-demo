"""Backend file logging helpers for packaged diagnostics."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config_service import get_default_user_data_dir

BACKEND_LOG_FILE_NAME = "backend.log"
MAX_BACKEND_LOG_BYTES = 2 * 1024 * 1024
BACKEND_LOG_BACKUP_COUNT = 3


def get_backend_log_path() -> Path:
    return get_default_user_data_dir() / "logs" / BACKEND_LOG_FILE_NAME


def configure_backend_logging() -> Path:
    log_path = get_backend_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    has_backend_file_handler = any(
        getattr(handler, "_linguasub_backend_file_handler", False)
        for handler in root_logger.handlers
    )
    if not has_backend_file_handler:
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=MAX_BACKEND_LOG_BYTES,
            backupCount=BACKEND_LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s [%(name)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        setattr(file_handler, "_linguasub_backend_file_handler", True)
        root_logger.addHandler(file_handler)

    logging.getLogger(__name__).info(
        "Backend logging configured path=%s frozen=%s executable=%s",
        log_path,
        bool(getattr(sys, "frozen", False)),
        sys.executable,
    )
    return log_path
