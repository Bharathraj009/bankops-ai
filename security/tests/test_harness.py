"""Safety regression tests; never start services or contact any endpoint."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("harness", ROOT / "security/run_step66.py")
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)


def test_environment_strips_credentials_and_implicit_targets(monkeypatch):
    for name in (
        "BANKOPS_DB_PASSWORD",
        "BANKOPS_AGENT_LLM_PROVIDER",
        "SPRING_DATASOURCE_URL",
        "POSTGRES_PASSWORD",
        "PGSERVICE",
        "GROQ_API_KEY",
        "OPENAI_API_KEY",
    ):
        monkeypatch.setenv(name, "untrusted")
    environment = harness.clean_environment()
    assert not any(
        environment.get(name) == "untrusted"
        for name in (
            "BANKOPS_DB_PASSWORD",
            "BANKOPS_AGENT_LLM_PROVIDER",
            "SPRING_DATASOURCE_URL",
            "POSTGRES_PASSWORD",
            "PGSERVICE",
            "GROQ_API_KEY",
            "OPENAI_API_KEY",
        )
    )


def test_opt_in_required_before_creating_fixtures(monkeypatch):
    monkeypatch.setattr(
        harness.argparse.ArgumentParser,
        "parse_args",
        lambda _: (_ for _ in ()).throw(SystemExit(2)),
    )
    monkeypatch.setattr(
        harness, "Harness", lambda: pytest.fail("Must not create fixtures without opt-in")
    )
    with pytest.raises(SystemExit):
        harness.main()


def test_credential_logs_are_redacted_and_failed_commands_are_not_retried(tmp_path, monkeypatch):
    from types import SimpleNamespace

    value = object.__new__(harness.Harness)
    value.keys = {"test": "private-ephemeral-fixture-key"}
    value.out = tmp_path
    value.environment = {}
    value.report = {"checks": {}}
    value.event = lambda *args: None
    calls = []

    def command(*args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=1, stdout=value.keys["test"], stderr="")

    monkeypatch.setattr(harness.subprocess, "run", command)
    with pytest.raises(harness.VerificationError):
        value.command("failure", ["synthetic"])
    assert len(calls) == 1
    assert (tmp_path / "failure.log").read_text() == "[REDACTED]"


def test_http_cannot_choose_remote_host(monkeypatch):
    seen = []

    class Response:
        status = 200
        headers = {}

        def read(self, limit):
            assert limit == 1048576
            return b"{}"

    class Opener:
        def open(self, request, timeout):
            seen.append(request.full_url)
            return Response()

    monkeypatch.setattr(harness.urllib.request, "build_opener", lambda *args: Opener())
    harness.http(18066, "/api/v1/customer/me")
    assert seen == ["http://127.0.0.1:18066/api/v1/customer/me"]


def test_only_expected_migrations_exist():
    files = harness.hashes()
    assert len(files) == 6
    assert all(any(name.startswith(f"V{version}__") for name in files) for version in range(1, 7))


def test_redirects_cannot_forward_credentials_to_remote_hosts():
    assert (
        harness.NoRedirect().redirect_request(
            None, None, 302, "Found", {}, "https://attacker.invalid"
        )
        is None
    )


def test_html_readiness_is_not_mistaken_for_malformed_json(monkeypatch):
    class Response:
        status = 200
        headers = {"Content-Type": "text/html"}

        def read(self, limit):
            return b"<!doctype html><html></html>"

    class Opener:
        def open(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr(harness.urllib.request, "build_opener", lambda *args: Opener())
    assert harness.http(5196, "/") == (200, None, {"Content-Type": "text/html"})
