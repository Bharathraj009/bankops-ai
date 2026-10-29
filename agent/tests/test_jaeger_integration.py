from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient
import pytest

from bankops_agent.app import create_app
from bankops_agent.config import Settings
from test_jaeger import make_span, payload


@contextmanager
def fake_jaeger(mode):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            from datetime import datetime

            requests.append((self.command, self.path, self.headers.get("Authorization")))
            params = parse_qs(urlsplit(self.path).query)
            end = datetime.fromisoformat(params["query.start_time_max"][0])
            data = payload([make_span(end, name="db.call", code=2)]) if mode == "ok" else {"result": {}}
            code = 200
            if mode == "error":
                data, code = {"error": "PRIVATE_SERVER_ERROR"}, 503
            elif mode == "notfound":
                data, code = {"error": {"httpCode": 404, "message": "No traces found"}}, 404
            body = json.dumps(data).encode()
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


@pytest.mark.parametrize("mode,status", [("ok", "ok"), ("empty", "missing"), ("notfound", "missing"), ("error", "unavailable")])
def test_real_http_evidence_route(monkeypatch, log_output, mode, status):
    with fake_jaeger(mode) as (port, requests):
        monkeypatch.setenv("BANKOPS_AGENT_JAEGER_URL", f"http://127.0.0.1:{port}/jaeger")
        monkeypatch.setenv("BANKOPS_AGENT_JAEGER_WINDOW_SECONDS", "60")
        logger, output = log_output
        with TestClient(create_app(Settings(), logger=logger)) as client:
            assert client.get("/health").status_code == 200 and not requests
            response = client.get("/evidence/traces", headers={"Authorization": "PRIVATE_CREDENTIAL"})
            assert response.status_code == 200 and response.json()["status"] == status
            assert response.headers["X-Correlation-ID"]
            assert len(requests) == 1 and requests[0][0] == "GET" and requests[0][2] is None
            assert urlsplit(requests[0][1]).path == "/jaeger/api/v3/traces"
            if mode == "ok":
                trace = response.json()["traces"][0]
                assert trace["failed"] and trace["slow_span_count"] == 1
            assert client.post("/evidence/traces").status_code == 405 and len(requests) == 1
        assert "PRIVATE" not in response.text and "PRIVATE" not in output.getvalue()
