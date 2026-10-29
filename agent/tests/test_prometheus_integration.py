"""Real HTTP integration against a local fake Prometheus, never a banking service."""

from contextlib import contextmanager
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient

from bankops_agent.app import create_app
from bankops_agent.config import Settings


@contextmanager
def prometheus_server():
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append((self.command, self.path))
            params = parse_qs(urlsplit(self.path).query)
            body = json.dumps({"status": "success", "data": {"resultType": "vector", "result": [
                {"metric": {}, "value": [float(params["time"][0]), "0.5"]}
            ]}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield server.server_address[1], requests
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


def test_real_http_collection_from_environment(monkeypatch, log_output):
    with prometheus_server() as (port, requests):
        monkeypatch.setenv("BANKOPS_AGENT_PROMETHEUS_URL", f"http://127.0.0.1:{port}/prometheus")
        logger, output = log_output
        with TestClient(create_app(Settings(), logger=logger)) as client:
            response = client.get("/evidence/prometheus")
            assert response.status_code == 200
            result = response.json()
            assert result["status"] == "ok"
            assert all(m["value"] == 0.5 and m["sampled_at"] for m in result["metrics"])
            assert len(requests) == 5
            assert all(method == "GET" and urlsplit(path).path == "/prometheus/api/v1/query" for method, path in requests)
        assert "prometheus/api" not in output.getvalue()


def test_real_connection_failure_returns_unavailable(log_output):
    # Reserve then close a local server socket to obtain a non-listening port.
    server = ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    port = server.server_address[1]
    server.server_close()
    logger, _ = log_output
    with TestClient(create_app(Settings(prometheus_url=f"http://127.0.0.1:{port}", prometheus_timeout_seconds=0.5), logger=logger)) as client:
        result = client.get("/evidence/prometheus")
        assert result.status_code == 200
        assert result.json()["status"] == "unavailable"
        assert all(m["status"] in ("unavailable", "timeout") and m["value"] is None for m in result.json()["metrics"])
        assert client.get("/health").status_code == 200
