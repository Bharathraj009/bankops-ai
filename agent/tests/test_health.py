from uuid import UUID, uuid4

from fastapi.testclient import TestClient
import pytest

from bankops_agent.app import create_app
from bankops_agent.config import Settings


def test_health_and_generated_correlation_id(log_output):
    logger, _ = log_output
    with TestClient(create_app(Settings(), logger=logger)) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "service": "bankops-reliability-agent"}
        value = response.headers["X-Correlation-ID"]
        assert str(UUID(value)) == value
        assert client.get("/health").headers["X-Correlation-ID"] != value
        assert client.get("/docs").status_code == 404


def test_propagates_valid_uuid(log_output):
    logger, _ = log_output
    value = str(uuid4())
    with TestClient(create_app(Settings(), logger=logger)) as client:
        response = client.get("/health", headers={"X-Correlation-ID": value.upper()})
        assert response.headers["X-Correlation-ID"] == value


@pytest.mark.parametrize("value", ["", "PRIVATE_USER@example.com", "x" * 1000, "bad\nlog-injection"])
def test_replaces_unsafe_correlation_ids(value, log_output):
    logger, output = log_output
    with TestClient(create_app(Settings(), logger=logger)) as client:
        response = client.get("/health", headers={"X-Correlation-ID": value})
        actual = response.headers["X-Correlation-ID"]
        assert str(UUID(actual)) == actual
        assert actual != value
        if value:
            assert value not in output.getvalue()


def test_replaces_duplicate_headers(log_output):
    logger, _ = log_output
    values = [str(uuid4()), str(uuid4())]
    with TestClient(create_app(Settings(), logger=logger)) as client:
        response = client.get("/health", headers=[("X-Correlation-ID", value) for value in values])
        assert response.headers["X-Correlation-ID"] not in values
