from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient
import pytest

from bankops_agent.app import create_app
from bankops_agent.config import Settings
from bankops_agent.evidence.prometheus import DETECTION_QUERIES
from test_detection import HEALTHY


@contextmanager
def fake_prometheus(values, fail):
    requests = []
    definitions = {expression: name for name, _, expression in DETECTION_QUERIES}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append((self.command, self.path))
            params = parse_qs(urlsplit(self.path).query)
            if fail:
                code, payload = 503, {"error": "PRIVATE_BACKEND_DETAIL"}
            else:
                value = values[definitions[params["query"][0]]]
                rows = [] if value is None else [{"metric": {}, "value": [float(params["time"][0]), str(value)]}]
                code, payload = 200, {"status": "success", "data": {"resultType": "vector", "result": rows}}
            body = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1], requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize("changed,fail,state,triggered", [
    ({}, False, "healthy", []),
    ({"api_error_rate": 0.2}, False, "incident", ["high_http_error_rate"]),
    ({"api_latency_p95": 2}, False, "incident", ["elevated_p95_latency"]),
    ({"transfer_failure_rate": 0.2}, False, "incident", ["high_transfer_failure_rate"]),
    ({"banking_availability": 0}, False, "incident", ["banking_unavailable"]),
    ({"banking_availability": None}, False, "insufficient_data", []),
    ({"api_latency_p95": None}, False, "insufficient_data", []),
    ({"api_request_rate": 0, "transfer_request_rate": 0}, False, "insufficient_data", []),
    ({"banking_availability": 0, "api_latency_p95": None}, False, "incident", ["banking_unavailable"]),
    ({}, True, "insufficient_data", []),
])
def test_detection_endpoint_uses_real_read_only_prometheus_http(monkeypatch, log_output, changed, fail, state, triggered):
    with fake_prometheus(HEALTHY | changed, fail) as (port, requests):
        monkeypatch.setenv("BANKOPS_AGENT_PROMETHEUS_URL", f"http://127.0.0.1:{port}")
        logger, output = log_output
        with TestClient(create_app(Settings(), logger=logger)) as client:
            assert client.get("/health").status_code == 200 and not requests
            response = client.get("/incidents/detect", headers={"Authorization": "PRIVATE_CREDENTIAL"})
            assert response.status_code == 200
            result = response.json()
            assert result["state"] == state and result["triggered_rules"] == triggered
            assert len(result["rules"]) == 4 and len(result["evidence"]["metrics"]) == 7
            assert result["detected_at"] and result["evidence"]["evaluated_at"]
            assert response.headers["X-Correlation-ID"]
            assert len(requests) == 7
            assert all(method == "GET" and urlsplit(path).path == "/api/v1/query" for method, path in requests)
            assert client.post("/incidents/detect").status_code == 405
            assert len(requests) == 7
        assert "PRIVATE" not in response.text and "PRIVATE" not in output.getvalue()


def test_environment_threshold_affects_http_endpoint(monkeypatch, log_output):
    with fake_prometheus(HEALTHY | {"api_error_rate": 0.1}, False) as (port, _):
        monkeypatch.setenv("BANKOPS_AGENT_PROMETHEUS_URL", f"http://127.0.0.1:{port}")
        monkeypatch.setenv("BANKOPS_AGENT_INCIDENT_HTTP_ERROR_RATIO", "0.2")
        logger, _ = log_output
        with TestClient(create_app(Settings(), logger=logger)) as client:
            assert client.get("/incidents/detect").json()["state"] == "healthy"
