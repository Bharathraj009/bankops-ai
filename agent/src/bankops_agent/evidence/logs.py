"""Bounded, read-only projection of trusted local ECS JSONL logs."""

import asyncio
import json
import os
from pathlib import Path
import re
import stat
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict

from bankops_agent.config import Settings


class LogEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    timestamp: datetime
    level: Literal["INFO", "WARN", "ERROR"]
    event_type: Literal["http_request_completed", "transfer_outcome"]
    correlation_id: str | None = None
    trace_id: str | None = None


class LogEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    source: Literal["local_jsonl"] = "local_jsonl"
    service: Literal["banking-service"] = "banking-service"
    collected_at: datetime
    window_start: datetime
    window_end: datetime
    status: Literal["ok", "missing", "not_configured", "unavailable", "partial"]
    truncated: bool = False
    events: list[LogEvent] = []


def _safe_path(path: Path) -> None:
    # Reject symlinks and Windows junctions/reparse points at every level.
    for part in (path, *path.parents):
        info = part.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise OSError("Unsupported source")


class LogCollector:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.path = None
        if settings.log_source_directory:
            directory = Path(settings.log_source_directory)
            # Relative and network sources are intentionally unsupported.
            if directory.is_absolute() and not str(directory).startswith(("\\\\", "//")):
                self.path = directory / settings.log_source_filename

    async def collect(self) -> LogEvidence:
        return await asyncio.to_thread(self._collect)

    def _collect(self) -> LogEvidence:
        now = datetime.now(UTC)
        start = now - timedelta(seconds=self.settings.log_window_seconds)
        result = dict(collected_at=now, window_start=start, window_end=now)
        if self.settings.log_source_directory is None:
            return LogEvidence(**result, status="not_configured")
        if self.path is None:
            return LogEvidence(**result, status="unavailable")
        try:
            _safe_path(self.path)
            before = self.path.stat()
            if not stat.S_ISREG(before.st_mode):
                raise OSError("Unsupported source")
            fd = os.open(self.path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(fd, "rb") as stream:
                opened = os.fstat(stream.fileno())
                _safe_path(self.path)
                if not stat.S_ISREG(opened.st_mode) or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
                    raise OSError("Source changed")
                offset = max(0, opened.st_size - self.settings.log_max_bytes)
                stream.seek(offset)
                data = stream.read(self.settings.log_max_bytes)
        except FileNotFoundError:
            return LogEvidence(**result, status="missing")
        except (OSError, ValueError):
            return LogEvidence(**result, status="unavailable")
        truncated = offset > 0
        if offset:
            data = data.partition(b"\n")[2]
        events = []
        malformed = False
        lines = data.splitlines()
        if len(lines) > 10000:
            truncated = True
            lines = lines[-10000:]
        for line in lines:
            if not line.strip():
                continue
            try:
                if len(line) > 16384:
                    raise ValueError("Oversize event")
                item = json.loads(line.decode("utf-8"))
                if not isinstance(item, dict):
                    raise ValueError("Invalid event")
                service = item.get("service")
                if not isinstance(service, dict) or service.get("name") != "banking-service":
                    continue
                log = item.get("log")
                if not isinstance(log, dict) or log.get("logger") != "com.bankops.banking.observability.SafeEventLogger":
                    continue
                levels = ("INFO", "WARN", "ERROR") if self.settings.log_include_info else ("WARN", "ERROR")
                if log.get("level") not in levels or item.get("event_type") not in ("http_request_completed", "transfer_outcome"):
                    continue
                timestamp = datetime.fromisoformat(item["@timestamp"].replace("Z", "+00:00"))
                if timestamp.tzinfo is None:
                    raise ValueError("Timezone required")
                if not start <= timestamp <= now:
                    continue
                correlation = item.get("correlation_id")
                trace = item.get("trace_id")
                events.append(LogEvent(
                    timestamp=timestamp, level=log["level"], event_type=item["event_type"],
                    correlation_id=correlation if isinstance(correlation, str) and re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", correlation) else None,
                    trace_id=trace if isinstance(trace, str) and re.fullmatch(r"[0-9a-f]{32}", trace) and trace != "0" * 32 else None,
                ))
            except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
                malformed = True
        events.sort(key=lambda event: event.timestamp, reverse=True)
        truncated |= len(events) > self.settings.log_max_events
        return LogEvidence(**result, status="partial" if malformed or truncated else ("ok" if events else "missing"),
                           truncated=truncated, events=events[:self.settings.log_max_events])
