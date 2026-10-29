import asyncio
from datetime import datetime
import json
import logging
from uuid import uuid4

from fastapi.testclient import TestClient
import httpx2 as httpx

from bankops_agent.app import create_app
from bankops_agent.config import Settings
from bankops_agent.logging import correlation_id, emit_event


def test_json_fields_and_sensitive_data_are_bounded(log_output):
    logger, output = log_output
    value = str(uuid4())
    with TestClient(create_app(Settings(), logger=logger)) as client:
        response = client.request("GET", "/health?password=PRIVATE_QUERY", headers={
            "X-Correlation-ID": value, "Authorization": "PRIVATE_CREDENTIAL",
            "Idempotency-Key": "PRIVATE_KEY",
        }, content='{"accountNumber":"PRIVATE_ACCOUNT","balance":987654.32}')
    event = json.loads(output.getvalue())
    assert response.status_code == 200
    assert set(event) == {"timestamp", "level", "service", "logger", "message", "event_type", "correlation_id", "http_status"}
    assert datetime.fromisoformat(event["timestamp"]).utcoffset().total_seconds() == 0
    assert event["level"] == "INFO"
    assert event["service"] == "bankops-reliability-agent"
    assert event["logger"] == "bankops_agent"
    assert event["message"] == "HTTP request completed"
    assert event["event_type"] == "http_request_completed"
    assert event["http_status"] == 200
    assert event["correlation_id"] == value
    for secret in ("PRIVATE_QUERY", "PRIVATE_CREDENTIAL", "PRIVATE_KEY", "PRIVATE_ACCOUNT", "987654.32", "/health"):
        assert secret not in output.getvalue()


def test_arbitrary_messages_extras_and_exceptions_are_not_rendered(log_output):
    logger, output = log_output
    logger.error("PRIVATE_MESSAGE", exc_info=ValueError("PRIVATE_EXCEPTION"))
    assert output.getvalue() == ""
    logger.info("PRIVATE_MESSAGE", extra={"event_type": "service_started", "credentials": "PRIVATE_EXTRA"})
    event = json.loads(output.getvalue())
    assert event["message"] == "Service started"
    assert event["correlation_id"] is None
    assert "PRIVATE" not in output.getvalue()


def test_404_and_unhandled_500_have_correlated_safe_logs(log_output):
    logger, output = log_output
    app = create_app(Settings(), logger=logger)

    @app.app.get("/explode")
    async def explode():
        raise ValueError("PRIVATE_EXCEPTION_DETAIL")

    with TestClient(app, raise_server_exceptions=False) as client:
        for path, status in (("/PRIVATE_PATH", 404), ("/explode", 500)):
            response = client.get(path)
            assert response.status_code == status
            event = json.loads(output.getvalue().splitlines()[-1])
            assert event["http_status"] == status
            assert event["correlation_id"] == response.headers["X-Correlation-ID"]
            assert "PRIVATE" not in response.text
    assert "PRIVATE" not in output.getvalue()
    assert correlation_id.get() is None


def test_concurrent_requests_keep_context_separate(log_output):
    logger, output = log_output
    app = create_app(Settings(), logger=logger)

    @app.app.get("/echo")
    async def echo():
        await asyncio.sleep(0)
        return {"correlation_id": correlation_id.get()}

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            values = [str(uuid4()) for _ in range(12)]
            responses = await asyncio.gather(*(client.get("/echo", headers={"X-Correlation-ID": value}) for value in values))
            for value, response in zip(values, responses, strict=True):
                assert response.headers["X-Correlation-ID"] == value
                assert response.json()["correlation_id"] == value
            assert correlation_id.get() is None
            return values

    values = asyncio.run(exercise())
    events = [json.loads(line) for line in output.getvalue().splitlines()]
    assert {event["correlation_id"] for event in events} == set(values)
    assert len(events) == len(values)


def test_logging_failure_cannot_change_health_or_leak_context():
    class BrokenHandler(logging.Handler):
        def emit(self, record):
            raise OSError("sink unavailable")

    logger = logging.Logger("broken")
    logger.addHandler(BrokenHandler())
    with TestClient(create_app(Settings(), logger=logger)) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.headers["X-Correlation-ID"]
    assert correlation_id.get() is None


def test_invalid_event_is_dropped(log_output):
    logger, output = log_output
    emit_event(logger, "PRIVATE_UNBOUNDED_EVENT")
    assert output.getvalue() == ""
