import asyncio
from datetime import UTC, datetime, timedelta
import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from bankops_agent.app import create_app
from bankops_agent.config import Settings
from bankops_agent.evidence.logs import LogCollector


def event(**changes):
    value = {"@timestamp": datetime.now(UTC).isoformat(),
             "service": {"name": "banking-service", "node": {}},
             "log": {"level": "ERROR", "logger": "com.bankops.banking.observability.SafeEventLogger"},
             "event_type": "transfer_outcome",
             "correlation_id": "12345678-1234-1234-1234-123456789abc",
             "trace_id": "abcdef0123456789abcdef0123456789",
             "message": "PRIVATE credentials account-id balance request-body",
             "error": {"stack_trace": "PRIVATE"}, "accountId": "PRIVATE", "transferId": "PRIVATE"}
    value.update(changes)
    return value


def collect(tmp_path, lines, **settings):
    source = tmp_path / "banking.jsonl"
    source.write_bytes(b"\n".join(json.dumps(line).encode() if isinstance(line, dict) else line for line in lines) + b"\n")
    before = source.read_bytes()
    result = asyncio.run(LogCollector(Settings(log_source_directory=str(tmp_path), **settings)).collect())
    assert source.read_bytes() == before
    return result


def test_projection_correlation_order_privacy(tmp_path):
    older = (datetime.now(UTC) - timedelta(seconds=20)).isoformat()
    result = collect(tmp_path, [event(**{"@timestamp": older}), event()])
    assert result.status == "ok"
    assert len(result.events) == 2
    assert result.events[0].timestamp > result.events[1].timestamp
    assert result.events[0].correlation_id == "12345678-1234-1234-1234-123456789abc"
    assert result.events[0].trace_id == "abcdef0123456789abcdef0123456789"
    assert set(result.events[0].model_dump()) == {"timestamp", "level", "event_type", "correlation_id", "trace_id"}
    assert "PRIVATE" not in result.model_dump_json()
    assert str(tmp_path) not in result.model_dump_json()


@pytest.mark.parametrize("changes", [
    {"service": {"name": "other"}}, {"service": "PRIVATE"},
    {"event_type": "PRIVATE"}, {"log": {"level": "ERROR", "logger": "PRIVATE"}},
    {"log": {"level": "INFO", "logger": "com.bankops.banking.observability.SafeEventLogger"}},
    {"@timestamp": (datetime.now(UTC) - timedelta(hours=2)).isoformat()},
    {"@timestamp": (datetime.now(UTC) + timedelta(hours=2)).isoformat()},
])
def test_excluded_events(tmp_path, changes):
    assert collect(tmp_path, [event(**changes)]).status == "missing"


@pytest.mark.parametrize("line", [b"not json", b"\xff", b"[]", b"x" * 17000,
                                     {"@timestamp": "invalid", **{k: v for k, v in event().items() if k != "@timestamp"}}])
def test_malformed_logs_partial_without_payload(tmp_path, line):
    result = collect(tmp_path, [line, event()])
    assert result.status == "partial"
    assert len(result.events) == 1
    assert "PRIVATE" not in result.model_dump_json()


def test_invalid_identifiers_are_omitted(tmp_path):
    result = collect(tmp_path, [event(correlation_id="PRIVATE", trace_id="PRIVATE")])
    assert result.events[0].correlation_id is None
    assert result.events[0].trace_id is None


def test_warn_http_event_and_http_malformed_evidence(tmp_path):
    source = tmp_path / "banking.jsonl"
    source.write_text("invalid\n" + json.dumps(event(
        event_type="http_request_completed",
        log={"level": "WARN", "logger": "com.bankops.banking.observability.SafeEventLogger"}
    )) + "\n", encoding="utf-8")
    with TestClient(create_app(Settings(log_source_directory=str(tmp_path)))) as client:
        response = client.get("/evidence/logs")
    assert response.status_code == 200
    assert response.json()["status"] == "partial"
    assert response.json()["events"][0]["level"] == "WARN"
    assert response.json()["events"][0]["event_type"] == "http_request_completed"
    assert "PRIVATE" not in response.text


def test_open_failure_sanitized(tmp_path, monkeypatch):
    (tmp_path / "banking.jsonl").write_text("", encoding="utf-8")
    def denied(*args, **kwargs):
        raise PermissionError("PRIVATE filesystem details")
    monkeypatch.setattr("bankops_agent.evidence.logs.os.open", denied)
    result = asyncio.run(LogCollector(Settings(log_source_directory=str(tmp_path))).collect())
    assert result.status == "unavailable"
    assert "PRIVATE" not in result.model_dump_json()


@pytest.mark.parametrize("directory", ["relative", "//server/share", "\\\\server\\share"])
def test_nonlocal_sources_rejected(directory):
    result = asyncio.run(LogCollector(Settings(log_source_directory=directory)).collect())
    assert result.status == "unavailable"


def test_result_and_byte_bounds(tmp_path):
    result = collect(tmp_path, [event() for _ in range(5)], log_max_events=2)
    assert result.status == "partial" and result.truncated and len(result.events) == 2
    result = collect(tmp_path, [event() for _ in range(20)], log_max_bytes=1024)
    assert result.status == "partial" and result.truncated
    assert 0 < len(result.events) < 20


def test_disabled_missing_directory_and_read_failure(tmp_path, monkeypatch):
    assert asyncio.run(LogCollector(Settings()).collect()).status == "not_configured"
    collector = LogCollector(Settings(log_source_directory=str(tmp_path)))
    assert asyncio.run(collector.collect()).status == "missing"
    (tmp_path / "banking.jsonl").mkdir()
    assert asyncio.run(collector.collect()).status == "unavailable"
    monkeypatch.setattr("bankops_agent.evidence.logs._safe_path", lambda path: (_ for _ in ()).throw(PermissionError("PRIVATE")))
    result = asyncio.run(collector.collect())
    assert result.status == "unavailable" and "PRIVATE" not in result.model_dump_json()


@pytest.mark.parametrize("filename", ["../secret", "C:\\secret", "/secret", "file:secret", "a/b", "a\\b", "", ".."])
def test_filename_restrictions(filename):
    with pytest.raises(ValidationError):
        Settings(log_source_filename=filename)


@pytest.mark.parametrize("setting,value", [("log_window_seconds", 0), ("log_window_seconds", 3601),
    ("log_max_events", 0), ("log_max_events", 501), ("log_max_bytes", 4194305)])
def test_configuration_bounds(setting, value):
    with pytest.raises(ValidationError):
        Settings(**{setting: value})


def test_symlink_rejected_without_following(tmp_path, monkeypatch):
    import stat
    from types import SimpleNamespace
    monkeypatch.setattr("pathlib.Path.lstat", lambda path: SimpleNamespace(st_mode=stat.S_IFLNK, st_file_attributes=0))
    result = asyncio.run(LogCollector(Settings(log_source_directory=str(tmp_path))).collect())
    assert result.status == "unavailable"


def test_http_endpoint_configured_source_and_path_rejection(tmp_path, monkeypatch, log_output):
    (tmp_path / "banking.jsonl").write_text(json.dumps(event()) + "\n", encoding="utf-8")
    monkeypatch.setenv("BANKOPS_AGENT_LOG_SOURCE_DIRECTORY", str(tmp_path))
    logger, output = log_output
    with TestClient(create_app(logger=logger)) as client:
        response = client.get("/evidence/logs")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert len(response.json()["events"]) == 1
        assert response.headers["X-Correlation-ID"]
        assert client.get("/evidence/logs?path=PRIVATE").status_code == 400
        assert client.post("/evidence/logs").status_code == 405
    assert "PRIVATE" not in response.text + output.getvalue()


@pytest.mark.parametrize("configured", [False, True])
def test_http_missing_sources(tmp_path, configured):
    settings = Settings(log_source_directory=str(tmp_path) if configured else None)
    with TestClient(create_app(settings)) as client:
        response = client.get("/evidence/logs")
    assert response.status_code == 200
    assert response.json()["status"] == ("missing" if configured else "not_configured")
    assert response.json()["events"] == []
