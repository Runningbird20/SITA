import logging
import sys

from pythonjsonlogger.json import JsonFormatter

from app.core.config import get_settings

_CONFIGURED = False


def configure_logging() -> None:
    """Configure root logging once, as structured JSON (or plain console output
    in local/dev via LOG_FORMAT=console). Every module should use
    `logging.getLogger(__name__)` rather than configuring its own handlers.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    settings = get_settings()
    handler = logging.StreamHandler(sys.stdout)

    if settings.log_format == "json":
        formatter = JsonFormatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            rename_fields={"asctime": "timestamp", "levelname": "level", "name": "logger"},
        )
    else:
        formatter = logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")

    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level.upper())

    # Quiet noisy third-party loggers down to the configured level's floor.
    logging.getLogger("uvicorn.access").setLevel(settings.log_level.upper())

    _CONFIGURED = True
