"""
SentinelTwin — Structured Logging
JSON structured logging for production observability
"""

import json
import sys
import logging
import logging.handlers
from datetime import datetime, timezone
from pathlib import Path


def setup_logging(
    level: str = "INFO",
    log_file: str = "./logs/sentineltwin.log",
    json_format: bool = True,
):
    """Configure structured logging for all SentinelTwin subsystems"""

    # Ensure log directory exists
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)

    # Root logger
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Clear existing handlers
    root.handlers.clear()

    if json_format:
        formatter = _JsonFormatter()
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s.%(msecs)03d [%(levelname)8s] %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    console.setLevel(logging.INFO)
    root.addHandler(console)

    # Rotating file handler
    file_handler = logging.handlers.TimedRotatingFileHandler(
        log_file,
        when="midnight",
        backupCount=90,
        encoding="utf-8",
        utc=True,
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)
    root.addHandler(file_handler)

    # Silence noisy libraries
    for noisy in ("uvicorn.access", "sqlalchemy.engine", "asyncio", "aioredis"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.getLogger("sentineltwin").setLevel(logging.DEBUG)


class _JsonFormatter(logging.Formatter):
    """JSON structured log formatter for machine parsing"""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        if hasattr(record, "request_id"):
            log_entry["request_id"] = record.request_id
        return json.dumps(log_entry, default=str)
