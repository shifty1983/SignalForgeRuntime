from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from src.common.paths import ensure_parent, logs_dir


DEFAULT_LOG_LEVEL = logging.INFO
DEFAULT_LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging(
    *,
    level: int = DEFAULT_LOG_LEVEL,
    log_file: str | Path | None = None,
) -> None:
    """
    Configure root logging for the application.

    Safe to call multiple times without duplicating handlers.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    formatter = logging.Formatter(
        DEFAULT_LOG_FORMAT,
        datefmt=DEFAULT_DATE_FORMAT,
    )

    if not any(isinstance(handler, logging.StreamHandler) for handler in root_logger.handlers):
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(level)
        root_logger.addHandler(console_handler)

    if log_file is not None:
        resolved_log_file = ensure_parent(log_file)

        already_has_file_handler = any(
            isinstance(handler, logging.FileHandler)
            and getattr(handler, "baseFilename", None) == str(resolved_log_file)
            for handler in root_logger.handlers
        )

        if not already_has_file_handler:
            file_handler = RotatingFileHandler(
                resolved_log_file,
                maxBytes=5_000_000,
                backupCount=5,
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            file_handler.setLevel(level)
            root_logger.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """
    Return a named logger.
    """
    return logging.getLogger(name)


def ingestion_logger(
    source_name: str,
    *,
    log_to_file: bool = True,
    level: int = DEFAULT_LOG_LEVEL,
) -> logging.Logger:
    """
    Return a source-specific ingestion logger.

    Example:
        logger = ingestion_logger("alpha_vantage")
        logger.info("Starting ingestion")
    """
    logger = get_logger(f"ingestion.{source_name}")
    logger.setLevel(level)
    logger.propagate = True

    if not log_to_file:
        return logger

    formatter = logging.Formatter(
        DEFAULT_LOG_FORMAT,
        datefmt=DEFAULT_DATE_FORMAT,
    )

    log_path = ensure_parent(logs_dir() / f"{source_name}.log")

    already_has_file_handler = any(
        isinstance(handler, logging.FileHandler)
        and getattr(handler, "baseFilename", None) == str(log_path)
        for handler in logger.handlers
    )

    if not already_has_file_handler:
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=5_000_000,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        logger.addHandler(file_handler)

    return logger
