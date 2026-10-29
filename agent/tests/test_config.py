import pytest
from pydantic import ValidationError

from bankops_agent.config import Settings


def test_defaults():
    settings = Settings()
    assert settings.environment == "dev"
    assert str(settings.host) == "127.0.0.1"
    assert settings.port == 8000
    assert settings.log_level == "INFO"


def test_environment_configuration_is_namespaced(monkeypatch):
    monkeypatch.setenv("BANKOPS_AGENT_ENVIRONMENT", "production")
    monkeypatch.setenv("BANKOPS_AGENT_HOST", "0.0.0.0")
    monkeypatch.setenv("BANKOPS_AGENT_PORT", "8123")
    monkeypatch.setenv("BANKOPS_AGENT_LOG_LEVEL", "WARNING")
    monkeypatch.setenv("BANKOPS_DB_PASSWORD", "PRIVATE_BANKING_CREDENTIAL")
    settings = Settings()
    assert settings.environment == "production"
    assert str(settings.host) == "0.0.0.0"
    assert settings.port == 8123
    assert settings.log_level == "WARNING"
    assert "PRIVATE_BANKING_CREDENTIAL" not in repr(settings)


@pytest.mark.parametrize(("field", "value"), [
    ("PORT", "0"), ("PORT", "65536"), ("PORT", "not-a-number"),
    ("ENVIRONMENT", "unknown"), ("LOG_LEVEL", "unknown"), ("HOST", "https://banking.example"),
])
def test_invalid_environment_fails_validation(monkeypatch, field, value):
    monkeypatch.setenv("BANKOPS_AGENT_" + field, value)
    with pytest.raises(ValidationError):
        Settings()


def test_no_implicit_dotenv_loading(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("BANKOPS_AGENT_PORT=8123\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert Settings().port == 8000


def test_invalid_startup_logs_only_safe_json(monkeypatch, capsys):
    import json
    from bankops_agent.main import run

    monkeypatch.setenv("BANKOPS_AGENT_PORT", "PRIVATE_INVALID_VALUE")
    with pytest.raises(SystemExit) as failure:
        run()
    assert failure.value.code == 2
    output = capsys.readouterr()
    event = json.loads(output.out)
    assert event["event_type"] == "configuration_invalid"
    assert event["level"] == "ERROR"
    assert "PRIVATE_INVALID_VALUE" not in output.out
    assert output.err == ""


@pytest.mark.parametrize(("field", "value"), [
    ("PROMETHEUS_URL", "file:///private"),
    ("PROMETHEUS_URL", "http://user:PRIVATE_PASSWORD@localhost:9090"),
    ("PROMETHEUS_URL", "http://localhost:9090?key=PRIVATE_KEY"),
    ("PROMETHEUS_URL", "http://localhost:9090/#private"),
    ("PROMETHEUS_TIMEOUT_SECONDS", "0"),
    ("PROMETHEUS_TIMEOUT_SECONDS", "31"),
    ("PROMETHEUS_TIMEOUT_SECONDS", "nan"),
])
def test_invalid_prometheus_configuration(monkeypatch, field, value):
    monkeypatch.setenv("BANKOPS_AGENT_" + field, value)
    with pytest.raises(ValidationError):
        Settings()
