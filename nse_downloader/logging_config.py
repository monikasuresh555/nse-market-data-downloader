"""
Logging configuration for NSE Market Data Downloader.

Produces consistent, structured logs containing required audit fields:
- timestamp
- dataset
- endpoint
- attempt number
- success/failure
- record count
- output path
- error message
"""

import json
import logging
import sys
from datetime import datetime
from typing import Any, Dict, Optional


class StructuredLogFormatter(logging.Formatter):
    """
    Formatter that outputs structured logs with contextual attributes.
    """

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.utcfromtimestamp(record.created).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        dataset = getattr(record, "dataset", "N/A")
        endpoint = getattr(record, "endpoint", "N/A")
        attempt = getattr(record, "attempt_number", "N/A")
        success = getattr(record, "success", None)
        record_count = getattr(record, "record_count", "N/A")
        output_path = getattr(record, "output_path", "N/A")
        error_msg = getattr(record, "error_message", record.getMessage() if record.levelno >= logging.ERROR else "")

        status_tag = ""
        if success is True:
            status_tag = " [SUCCESS]"
        elif success is False:
            status_tag = " [FAILURE]"

        base_msg = (
            f"[{timestamp}] [{record.levelname:7s}]{status_tag} "
            f"dataset={dataset} | endpoint={endpoint} | attempt={attempt} | "
            f"records={record_count} | path={output_path} | {record.getMessage()}"
        )

        if error_msg and error_msg != record.getMessage():
            base_msg += f" | error={error_msg}"

        return base_msg


def setup_logger(
    name: str = "nse_downloader",
    level: str = "INFO",
    log_file: Optional[str] = None,
) -> logging.Logger:
    """
    Configure and return a structured application logger.

    Args:
        name: Logger name.
        level: Logging level (DEBUG, INFO, WARNING, ERROR).
        log_file: Optional path to append log entries.

    Returns:
        Configured logging.Logger instance.
    """
    logger = logging.getLogger(name)
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(numeric_level)

    # Clear existing handlers to prevent duplicates
    if logger.hasHandlers():
        logger.handlers.clear()

    formatter = StructuredLogFormatter()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Optional file handler
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    logger.propagate = False
    return logger


def log_event(
    logger: logging.Logger,
    level: int,
    message: str,
    dataset: str = "N/A",
    endpoint: str = "N/A",
    attempt_number: Any = "N/A",
    success: Optional[bool] = None,
    record_count: Any = "N/A",
    output_path: str = "N/A",
    error_message: str = "",
) -> None:
    """
    Helper function to log an event with all mandatory metadata fields.
    """
    extra: Dict[str, Any] = {
        "dataset": dataset,
        "endpoint": endpoint,
        "attempt_number": attempt_number,
        "success": success,
        "record_count": record_count,
        "output_path": output_path,
        "error_message": error_message,
    }
    logger.log(level, message, extra=extra)
