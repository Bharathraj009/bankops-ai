"""Bounded JSON events: arbitrary messages, bodies and exceptions are never rendered."""

from contextvars import ContextVar
from datetime import datetime, timezone
import json
import logging
import re
import sys
from typing import TextIO

from bankops_agent.config import SERVICE_NAME

correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)
UUID_PATTERN = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\Z")
MESSAGES = {"http_request_completed": "HTTP request completed", "service_started": "Service started",
            "configuration_invalid": "Invalid agent configuration"}


class EventFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return getattr(record, "event_type", None) in MESSAGES


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        event = record.event_type
        value = correlation_id.get()
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "service": SERVICE_NAME,
            "logger": "bankops_agent",
            "message": MESSAGES[event],
            "event_type": event,
            "correlation_id": value if value and UUID_PATTERN.fullmatch(value) else None,
        }
        if event == "http_request_completed":
            status = getattr(record, "http_status", 500)
            payload["http_status"] = status if type(status) is int and 100 <= status <= 599 else 500
        return json.dumps(payload, separators=(",", ":"))


def create_logger(level: str = "INFO", stream: TextIO | None = None) -> logging.Logger:
    # A private logger per application instance avoids global handlers and duplicate test/app logs.
    logger = logging.Logger("bankops_agent", level=level)
    logger.propagate = False
    handler = logging.StreamHandler(stream if stream is not None else sys.stdout)
    handler.addFilter(EventFilter())
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    return logger


def emit_event(logger: logging.Logger, event: str, *, status: int = 200) -> None:
    if event not in MESSAGES:
        return
    try:
        level = logging.ERROR if event == "configuration_invalid" else logging.INFO
        logger.log(level, MESSAGES[event], extra={"event_type": event, "http_status": status})
    except Exception:
        # A failed handler must not change the response or leak request context.
        pass
