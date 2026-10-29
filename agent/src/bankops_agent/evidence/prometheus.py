"""Fixed aggregate instant queries. Never return labels, raw payloads or remote error text."""

import asyncio
from datetime import datetime, timezone
import json
import math
from typing import Literal

import httpx2 as httpx
from pydantic import BaseModel, ConfigDict

from bankops_agent.config import Settings

API_COUNT = 'http_server_requests_seconds_count{job="banking-service",uri=~"/api/v1/.*"}'
TRANSFER = 'bankops_transfer_outcomes_total{job="banking-service",operation="transfer"'
API_RATE = f"sum(rate({API_COUNT}[5m]))"
TRANSFER_RATE = f"sum(rate({TRANSFER}}}[5m]))"
# Kept aligned with the provisioned dashboard; no user-supplied PromQL or label values.
QUERIES = (
    ("api_request_rate", "requests_per_second", API_RATE),
    ("api_error_rate", "ratio", f'(sum(rate(http_server_requests_seconds_count{{job="banking-service",uri=~"/api/v1/.*",status=~"4..|5.."}}[5m])) or (0 * {API_RATE})) / clamp_min({API_RATE}, 1e-12)'),
    ("api_latency_p95", "seconds", 'histogram_quantile(0.95, sum by (le) (rate(http_server_requests_seconds_bucket{job="banking-service",uri=~"/api/v1/.*"}[5m])))'),
    ("transfer_success_rate", "requests_per_second", f'sum(rate({TRANSFER},outcome="completed"}}[5m])) or (0 * {TRANSFER_RATE})'),
    ("transfer_failure_rate", "requests_per_second", f'sum(rate({TRANSFER},outcome=~"invalid_request|account_not_found|idempotency_conflict|rejected|server_error|other"}}[5m])) or (0 * {TRANSFER_RATE})'),
)

DETECTION_QUERIES = QUERIES + (
    ("banking_availability", "ratio", 'min(up{job="banking-service"})'),
    ("transfer_request_rate", "requests_per_second", TRANSFER_RATE),
)


class MetricEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: Literal["api_request_rate", "api_error_rate", "api_latency_p95", "transfer_success_rate", "transfer_failure_rate", "banking_availability", "transfer_request_rate"]
    unit: Literal["requests_per_second", "ratio", "seconds"]
    status: Literal["ok", "missing", "timeout", "unavailable", "query_error", "invalid_response"]
    value: float | None = None
    sampled_at: datetime | None = None


class PrometheusEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    source: Literal["prometheus"] = "prometheus"
    service: Literal["banking-service"] = "banking-service"
    window: Literal["5m"] = "5m"
    evaluated_at: datetime
    collected_at: datetime
    status: Literal["ok", "partial", "unavailable"]
    metrics: tuple[MetricEvidence, ...]


class PrometheusCollector:
    def __init__(self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.url = str(settings.prometheus_url).rstrip("/") + "/api/v1/query"
        self.timeout = settings.prometheus_timeout_seconds
        self.transport = transport

    async def collect(self) -> PrometheusEvidence:
        return await self._collect(QUERIES)

    async def collect_for_detection(self) -> PrometheusEvidence:
        return await self._collect(DETECTION_QUERIES)

    async def _collect(self, definitions) -> PrometheusEvidence:
        evaluated = datetime.now(timezone.utc)
        async with httpx.AsyncClient(transport=self.transport, timeout=self.timeout, follow_redirects=False,
                                     trust_env=False, limits=httpx.Limits(max_connections=len(definitions), max_keepalive_connections=len(definitions))) as client:
            metrics = tuple(await asyncio.gather(*(self._query(client, definition, evaluated) for definition in definitions)))
        count = sum(metric.status == "ok" for metric in metrics)
        return PrometheusEvidence(evaluated_at=evaluated, collected_at=datetime.now(timezone.utc),
                                  status="ok" if count == len(definitions) else "partial" if count else "unavailable", metrics=metrics)

    async def _query(self, client, definition, evaluated) -> MetricEvidence:
        name, unit, expression = definition

        def result(status, **values):
            return MetricEvidence(name=name, unit=unit, status=status, **values)

        try:
            # Wall-clock deadline also bounds slow streamed responses; HTTP phase timeouts alone do not.
            async with asyncio.timeout(self.timeout):
                async with client.stream("GET", self.url, params={"query": expression, "time": evaluated.timestamp(),
                                                                 "timeout": f"{max(1, int(self.timeout * 1000))}ms"}) as response:
                    if response.status_code != 200:
                        return result("unavailable")
                    payload = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(payload) + len(chunk) > 65536:
                            return result("invalid_response")
                        payload.extend(chunk)
                data = json.loads(payload)
                if not isinstance(data, dict):
                    return result("invalid_response")
                # Warnings/infos may indicate incomplete data. Do not accept a misleading numeric value.
                if data.get("status") == "error" or data.get("warnings") or data.get("infos"):
                    return result("query_error")
                if data.get("status") != "success":
                    return result("invalid_response")
                vector = data["data"]
                if vector["resultType"] != "vector" or not isinstance(vector["result"], list):
                    return result("invalid_response")
                rows = vector["result"]
                if not rows:
                    return result("missing")
                if len(rows) != 1 or rows[0].get("metric") != {}:
                    return result("invalid_response")
                sample = rows[0]["value"]
                if not isinstance(sample, list) or len(sample) != 2 or type(sample[0]) not in (int, float) or not isinstance(sample[1], str):
                    return result("invalid_response")
                value = float(sample[1])
                if not math.isfinite(value):
                    return result("missing")
                sampled = datetime.fromtimestamp(sample[0], timezone.utc)
                age = (evaluated - sampled).total_seconds()
                if age < -1 or age > 300 or value < 0 or (name == "api_error_rate" and value > 1) or (name == "banking_availability" and value not in (0, 1)):
                    return result("invalid_response")
                return result("ok", value=value, sampled_at=sampled)
        except (TimeoutError, httpx.TimeoutException):
            return result("timeout")
        except httpx.HTTPError:
            return result("unavailable")
        except (ValueError, TypeError, KeyError, IndexError, AttributeError, OverflowError, RecursionError):
            return result("invalid_response")
