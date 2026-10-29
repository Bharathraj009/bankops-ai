"""Bounded Jaeger v3 OTLP search, projecting only explicitly safe fields."""

import asyncio
from datetime import datetime, timedelta, timezone
import json
import re
from typing import Literal

import httpx2 as httpx
from pydantic import BaseModel, ConfigDict

from bankops_agent.config import Settings

SAFE_NAMES = {"http.request", "transfer.create", "transfer.read", "transfer.fund", "db.call"}
MAX_RESPONSE_BYTES = 1024 * 1024


class SpanEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    span_id: str
    name: Literal["http.request", "transfer.create", "transfer.read", "transfer.fund", "db.call", "other"]
    service: Literal["banking-service"] = "banking-service"
    started_at: datetime
    duration_seconds: float
    failed: bool
    slow: bool


class TraceEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    trace_id: str
    service: Literal["banking-service"] = "banking-service"
    started_at: datetime
    duration_seconds: float
    failed: bool
    slow_span_count: int
    failed_span_count: int
    truncated: bool
    spans: tuple[SpanEvidence, ...]


class JaegerEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    source: Literal["jaeger"] = "jaeger"
    service: Literal["banking-service"] = "banking-service"
    window_start: datetime
    window_end: datetime
    collected_at: datetime
    slow_span_seconds: float
    status: Literal["ok", "missing", "partial", "timeout", "unavailable", "invalid_response"]
    truncated: bool = False
    traces: tuple[TraceEvidence, ...] = ()


def identifier(value, length):
    return isinstance(value, str) and re.fullmatch(f"[0-9a-f]{{{length}}}", value) is not None and int(value, 16) != 0


def nanoseconds(value):
    if type(value) is int:
        number = value
    elif isinstance(value, str) and re.fullmatch(r"[0-9]{1,20}", value):
        number = int(value)
    else:
        raise ValueError("Invalid timestamp")
    if not 0 <= number <= 2**64 - 1:
        raise ValueError("Invalid timestamp")
    return number


class JaegerCollector:
    def __init__(self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self.url = str(settings.jaeger_url).rstrip("/") + "/api/v3/traces"
        self.transport = transport

    async def collect(self) -> JaegerEvidence:
        end = datetime.now(timezone.utc)
        start = end - timedelta(seconds=self.settings.jaeger_window_seconds)

        def result(status, **values):
            return JaegerEvidence(window_start=start, window_end=end, collected_at=datetime.now(timezone.utc),
                                  slow_span_seconds=self.settings.jaeger_slow_span_seconds, status=status, **values)

        try:
            async with asyncio.timeout(self.settings.jaeger_timeout_seconds):
                async with httpx.AsyncClient(transport=self.transport, timeout=self.settings.jaeger_timeout_seconds,
                                             follow_redirects=False, trust_env=False) as client:
                    async with client.stream("GET", self.url, params={
                        "query.service_name": "banking-service", "query.start_time_min": start.isoformat(),
                        "query.start_time_max": end.isoformat(), "query.search_depth": self.settings.jaeger_max_traces,
                        "query.raw_traces": "true",
                    }) as response:
                        if response.status_code not in (200, 404):
                            return result("unavailable")
                        code = response.status_code
                        payload = bytearray()
                        async for chunk in response.aiter_bytes():
                            if len(payload) + len(chunk) > MAX_RESPONSE_BYTES:
                                return result("invalid_response", truncated=True)
                            payload.extend(chunk)
                if code == 404:
                    try:
                        error = json.loads(payload).get("error", {})
                        empty = error.get("httpCode") == 404 and error.get("message") == "No traces found"
                    except (ValueError, TypeError, AttributeError):
                        empty = False
                    return result("missing" if empty else "unavailable")
                # gRPC-gateway can return one or several newline-delimited result envelopes.
                try:
                    documents = [json.loads(payload)]
                except json.JSONDecodeError:
                    documents = [json.loads(line) for line in payload.splitlines() if line.strip()]
                if not documents:
                    return result("invalid_response")
                traces, truncated, invalid = self._project(documents, start, end)
                return result("partial" if truncated or invalid else "ok" if traces else "missing",
                              traces=traces, truncated=truncated)
        except (TimeoutError, httpx.TimeoutException):
            return result("timeout")
        except httpx.HTTPError:
            return result("unavailable")
        except (ValueError, TypeError, KeyError, AttributeError, IndexError, OverflowError, RecursionError):
            return result("invalid_response")

    def _project(self, documents, start, end):
        grouped, seen = {}, set()
        total, truncated, invalid = 0, False, False
        lower = int(start.timestamp()) * 1_000_000_000 + start.microsecond * 1000
        upper = int(end.timestamp()) * 1_000_000_000 + end.microsecond * 1000
        for document in documents:
            if not isinstance(document, dict) or "error" in document:
                raise ValueError("Invalid envelope")
            resources = document["result"].get("resourceSpans", [])
            if not isinstance(resources, list):
                raise ValueError("Invalid resources")
            for resource in resources:
                attributes = resource["resource"].get("attributes", [])
                services = [a.get("value", {}).get("stringValue") for a in attributes if a.get("key") == "service.name"]
                if services != ["banking-service"]:
                    continue
                for scope in resource.get("scopeSpans", []):
                    for span in scope.get("spans", []):
                        try:
                            trace_id, span_id = span["traceId"], span["spanId"]
                            if not identifier(trace_id, 32) or not identifier(span_id, 16):
                                raise ValueError("Invalid identifier")
                            first, last = nanoseconds(span["startTimeUnixNano"]), nanoseconds(span["endTimeUnixNano"])
                            if last < first:
                                raise ValueError("Invalid interval")
                            if first < lower or first >= upper or last > upper:
                                continue
                            if (trace_id, span_id) in seen:
                                invalid = True
                                continue
                            seen.add((trace_id, span_id))
                            if trace_id not in grouped:
                                if len(grouped) >= self.settings.jaeger_max_traces:
                                    truncated = True
                                    continue
                                grouped[trace_id] = {"spans": [], "starts": [], "ends": [], "truncated": False}
                            group = grouped[trace_id]
                            if total >= self.settings.jaeger_max_total_spans or len(group["spans"]) >= self.settings.jaeger_max_spans_per_trace:
                                group["truncated"] = truncated = True
                                continue
                            status = span.get("status", {}).get("code", 0)
                            if type(status) not in (int, str) or status not in (0, 1, 2, "STATUS_CODE_UNSET", "STATUS_CODE_OK", "STATUS_CODE_ERROR"):
                                raise ValueError("Invalid span status")
                            failed = status in (2, "STATUS_CODE_ERROR")
                            # Read only the bounded numeric status indicator, never other attributes/messages/events.
                            for a in span.get("attributes", []):
                                if a.get("key") == "http.response.status_code":
                                    code = a.get("value", {}).get("intValue")
                                    if isinstance(code, (str, int)) and str(code).isdigit() and len(str(code)) == 3:
                                        failed = failed or 500 <= int(code) <= 599
                            duration = (last - first) / 1_000_000_000
                            name = span.get("name")
                            group["spans"].append(SpanEvidence(span_id=span_id, name=name if isinstance(name, str) and name in SAFE_NAMES else "other",
                                started_at=datetime.fromtimestamp(first // 1_000_000_000, timezone.utc).replace(microsecond=(first % 1_000_000_000) // 1000),
                                duration_seconds=duration, failed=failed, slow=duration >= self.settings.jaeger_slow_span_seconds))
                            group["ends"].append(last)
                            group["starts"].append(first)
                            total += 1
                        except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
                            invalid = True
        traces = []
        for trace_id, group in grouped.items():
            spans = tuple(sorted(group["spans"], key=lambda s: (s.started_at, s.span_id)))
            if not spans:
                continue
            began = min(s.started_at for s in spans)
            failures = sum(s.failed for s in spans)
            traces.append(TraceEvidence(trace_id=trace_id, started_at=began, duration_seconds=(max(group["ends"]) - min(group["starts"])) / 1_000_000_000,
                failed=failures > 0, slow_span_count=sum(s.slow for s in spans), failed_span_count=failures,
                truncated=group["truncated"], spans=spans))
        return tuple(sorted(traces, key=lambda t: (t.started_at, t.trace_id), reverse=True)), truncated, invalid
