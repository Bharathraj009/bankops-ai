"""Repeatable local security regression. All writes target newly created fixtures.

Opt-in required. No development services/roles, paid inference or production
targets. Secrets stay in child environments; reports contain only safe results.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
FRONT = ROOT / "frontend"
PYTHON = ROOT / "agent/.venv/Scripts/python.exe"
JAVA = Path(os.environ.get("JAVA_HOME", "C:/Program Files/Java/jdk-25")) / "bin/java.exe"
JAR = ROOT / "backend/banking-service/target/banking-service-0.0.1-SNAPSHOT.jar"
IMAGE = "bankops-airflow-step63-tests"


class VerificationError(Exception):
    """Only a bounded stage name is safe to publish."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, url):
        return None


def clean_environment():
    prefixes = (
        "BANKOPS_",
        "SPRING_",
        "VITE_",
        "POSTGRES_",
        "PG",
        "OTEL_",
        "OPENAI_",
        "GROQ_",
        "ANTHROPIC_",
        "AWS_",
    )
    return {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(prefixes)
        and k not in ("DATABASE_URL", "DATABASE_PASSWORD", "DB_PASSWORD", "DB_ADMIN_DSN")
    }


def hashes():
    paths = sorted(
        (ROOT / "backend/banking-service/src/main/resources/db/migration").glob("V*__*.sql")
    )
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def http(port, path, method="GET", token=None, body=None, key=None, headers=None):
    values = {"Content-Type": "application/json", **(headers or {})}
    if token:
        values["Authorization"] = "Bearer " + token
    if key:
        values["Idempotency-Key"] = key
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}" + path,
        data=None if body is None else json.dumps(body).encode(),
        headers=values,
        method=method,
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        response = opener.open(request, timeout=15)
    except urllib.error.HTTPError as error:
        response = error
    raw = response.read(1048576)
    content_type = response.headers.get("Content-Type", "")
    body = json.loads(raw) if raw and ("/json" in content_type or "+json" in content_type) else None
    return response.status, body, dict(response.headers)


class Harness:
    def __init__(self):
        self.run_id = uuid4().hex[:12]
        self.out = FRONT / ".cache/step66" / self.run_id
        self.out.mkdir(parents=True)
        (self.out / "tmp").mkdir()
        self.keys = {
            name: secrets.token_urlsafe(40)
            for name in (
                "admin",
                "migration",
                "runtime",
                "reader",
                "operator",
                "deployment",
                "proposer",
                "reviewer",
                "regression",
            )
        }
        self.containers = []
        self.children = []
        self.logs = []
        self.report = {"run_id": self.run_id, "status": "RUNNING", "checks": {}}
        self.environment = clean_environment() | {
            "PYTHONDONTWRITEBYTECODE": "1",
            "TEMP": str(self.out / "tmp"),
            "TMP": str(self.out / "tmp"),
        }
        self.before = hashes()
        self.bank_container = f"bankops-step66-{self.run_id}-banking"
        self.reg_container = f"bankops-step66-{self.run_id}-regression"

    def event(self, stage, status):
        print(json.dumps({"stage": stage, "status": status}), flush=True)

    def command(self, stage, command, *, cwd=ROOT, env=None, allowed=(0,), timeout=600):
        self.event(stage, "RUNNING")
        result = subprocess.run(
            command,
            cwd=cwd,
            env=self.environment | (env or {}),
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        text = result.stdout + result.stderr
        for secret in self.keys.values():
            text = text.replace(secret, "[REDACTED]")
        (self.out / (stage + ".log")).write_text(text, encoding="utf-8")
        if result.returncode not in allowed:
            raise VerificationError(stage)
        self.report["checks"][stage] = {"exit_code": result.returncode}
        self.event(stage, "PASS")
        return text

    def container(self, name, port, user, database, password, hba=False):
        command = [
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "-e",
            "POSTGRES_PASSWORD",
            "-e",
            "POSTGRES_USER=" + user,
            "-e",
            "POSTGRES_DB=" + database,
            "-p",
            f"127.0.0.1:{port}:5432",
        ]
        if hba:
            command += [
                "-e",
                "POSTGRES_INITDB_ARGS=--auth-host=scram-sha-256 --auth-local=scram-sha-256",
                "-v",
                str(ROOT / "database/pg_hba.conf") + ":/etc/postgresql/policy.conf:ro",
            ]
        command += [
            "postgres:16" if hba else "postgres:17",
            "-c",
            "log_statement=none",
            "-c",
            "log_min_error_statement=panic",
        ]
        if hba:
            command += ["-c", "hba_file=/etc/postgresql/policy.conf"]
        self.command(
            "create-" + ("banking" if hba else "regression"),
            command,
            env={"POSTGRES_PASSWORD": password},
        )
        self.containers.append(name)
        for _ in range(60):
            result = subprocess.run(
                ["docker", "exec", name, "pg_isready", "-U", user, "-d", database],
                capture_output=True,
            )
            if result.returncode == 0:
                return
            time.sleep(0.5)
        raise VerificationError("postgres-readiness")

    def tooling(self, stage, script, operation=None, extra=None):
        env = {
            "BANKOPS_DB_SECURITY_APPLY": "local-only",
            "BANKOPS_DB_NAME": "bankops",
            "BANKOPS_DB_ADMIN_DSN": f"host=host.docker.internal port=55466 dbname=bankops user=bankops password={self.keys['admin']}",
            "BANKOPS_DB_PASSWORD": self.keys["runtime"],
            "BANKOPS_MIGRATION_DB_PASSWORD": self.keys["migration"],
            "BANKOPS_RECONCILIATION_PASSWORD": self.keys["reader"],
            "BANKOPS_SECURITY_E2E": "step66-isolated",
            **(extra or {}),
        }
        command = [
            "docker",
            "run",
            "--rm",
            "-e",
            "PYTHONDONTWRITEBYTECODE=1",
            "-e",
            "PYTHONPATH=/workspace/airflow",
        ]
        for name in env:
            command += ["-e", name]
        command += ["-v", str(ROOT) + ":/workspace:ro", "-w", "/workspace", IMAGE, "python", script]
        if operation:
            command.append(operation)
        return self.command(stage, command, env=env)

    def start(self, label, command, cwd, env):
        log = (self.out / (label + ".log")).open("w", encoding="utf-8")
        self.logs.append(log)
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=self.environment | env,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        self.children.append(process)
        return process

    def ready(self, port, path):
        for _ in range(120):
            if any(p.poll() is not None for p in self.children):
                raise VerificationError("service-startup")
            try:
                if http(port, path)[0] == 200:
                    return
            except (OSError, ValueError):
                pass
            time.sleep(0.5)
        raise VerificationError("service-readiness")

    def regressions(self):
        self.container(
            self.reg_container, 55467, "bankops_test", "bankops_test", self.keys["regression"]
        )
        maven = next((Path.home() / ".m2/wrapper/dists").glob("apache-maven-*/**/bin/mvn.cmd"))
        bank_env = {
            "JAVA_HOME": str(JAVA.parent.parent),
            "BANKOPS_TEST_DB_URL": "jdbc:postgresql://127.0.0.1:55467/bankops_test",
            "BANKOPS_TEST_DB_USER": "bankops_test",
            "BANKOPS_TEST_DB_PASSWORD": self.keys["regression"],
        }
        self.command(
            "banking-tests",
            [str(maven), "-Dmaven.repo.local=" + str(Path.home() / ".m2/repository"), "package"],
            cwd=ROOT / "backend/banking-service",
            env=bank_env,
        )
        self.command(
            "agent-tests", [str(PYTHON), "-m", "pytest", "-q", "-W", "error"], cwd=ROOT / "agent"
        )
        dsn = f"host=host.docker.internal port=55467 dbname=bankops_test user=bankops_test password={self.keys['regression']}"
        self.command(
            "airflow-tests",
            [
                "docker",
                "run",
                "--rm",
                "-e",
                "PYTHONDONTWRITEBYTECODE=1",
                "-e",
                "PYTHONPATH=/workspace/airflow",
                "-e",
                "BANKOPS_RECONCILIATION_TEST_DSN",
                "-v",
                str(ROOT) + ":/workspace:ro",
                "-w",
                "/workspace/airflow",
                IMAGE,
                "python",
                "-m",
                "pytest",
                "-q",
                "-W",
                "error",
                "-p",
                "no:cacheprovider",
            ],
            env={"BANKOPS_RECONCILIATION_TEST_DSN": dsn},
        )
        self.command(
            "database-tests",
            [
                "docker",
                "run",
                "--rm",
                "-e",
                "PYTHONDONTWRITEBYTECODE=1",
                "-e",
                "BANKOPS_DATABASE_SECURITY_TEST_DSN",
                "-v",
                str(ROOT) + ":/workspace:ro",
                "-w",
                "/workspace",
                IMAGE,
                "python",
                "-m",
                "pytest",
                "database/tests",
                "database/integration",
                "-q",
                "-W",
                "error",
                "-p",
                "no:cacheprovider",
            ],
            env={"BANKOPS_DATABASE_SECURITY_TEST_DSN": dsn},
        )
        self.command(
            "harness-tests", [str(PYTHON), "-m", "pytest", "security/tests", "-q", "-W", "error"]
        )
        self.command(
            "python-lint",
            [str(PYTHON), "-m", "ruff", "check", "--config", "security/ruff.toml", "security"],
        )
        self.command(
            "python-format",
            [
                str(PYTHON),
                "-m",
                "ruff",
                "format",
                "--check",
                "--config",
                "security/ruff.toml",
                "security",
            ],
        )
        npm = shutil.which("npm.cmd") or "npm"
        for task in ("lint", "typecheck", "format:check", "test", "build", "test:e2e"):
            self.command("frontend-" + task.replace(":", "-"), [npm, "run", task], cwd=FRONT)

    def integration(self):
        self.container(
            self.bank_container, 55466, "bankops", "bankops", self.keys["admin"], hba=True
        )
        self.tooling("prepare-roles", "database/provision.py", "prepare")
        migration = {
            "BANKOPS_MIGRATION_DB_USER": "bankops_migrator",
            "BANKOPS_MIGRATION_DB_PASSWORD": self.keys["migration"],
            "BANKOPS_MIGRATION_DB_URL": "jdbc:postgresql://127.0.0.1:55466/bankops",
            "BANKOPS_MIGRATION_APPLY": "local-only",
        }
        launcher = [
            str(JAVA),
            "-Dloader.main=com.bankops.banking.security.DatabaseMigration",
            "-cp",
            str(JAR),
            "org.springframework.boot.loader.launch.PropertiesLauncher",
        ]
        self.command("dedicated-migration", launcher, env=migration)
        self.command("migration-repeat-validate", launcher, env=migration)
        self.tooling("grant-runtime", "database/provision.py", "grant")
        runtime = {
            "BANKOPS_DB_URL": "jdbc:postgresql://127.0.0.1:55466/bankops",
            "BANKOPS_DB_USER": "bankops_runtime",
            "BANKOPS_DB_PASSWORD": self.keys["runtime"],
            "BANKOPS_CUSTOMER_ENABLED": "true",
            "BANKOPS_BANKING_API_TOKEN": self.keys["operator"],
            "BANKOPS_DEV_FUNDING_ACCOUNT_ID": str(uuid4()),
            "BANKOPS_DEV_RESERVE_BOOTSTRAP_ENABLED": "true",
            "BANKOPS_DEV_RESERVE_INITIAL_BALANCE": "10000.00",
        }
        assert (
            "BANKOPS_MIGRATION_DB_PASSWORD" not in runtime and "BANKOPS_DB_ADMIN_DSN" not in runtime
        )
        self.command(
            "administrator-runtime-startup-denied",
            [
                str(JAVA),
                "-jar",
                str(JAR),
                "--spring.profiles.active=dev,db-secure",
                "--server.port=18068",
            ],
            env=runtime
            | {
                "BANKOPS_DB_USER": "bankops",
                "BANKOPS_DB_PASSWORD": self.keys["admin"],
                "BANKOPS_DEV_RESERVE_BOOTSTRAP_ENABLED": "false",
            },
            allowed=(1,),
            timeout=60,
        )
        self.start(
            "banking-service",
            [
                str(JAVA),
                "-jar",
                str(JAR),
                "--spring.profiles.active=dev,db-secure",
                "--server.port=18066",
            ],
            ROOT,
            runtime,
        )
        self.ready(18066, "/actuator/health")
        agent = {
            "BANKOPS_AGENT_ENVIRONMENT": "test",
            "BANKOPS_AGENT_PORT": "18067",
            "BANKOPS_AGENT_HOST": "127.0.0.1",
            "BANKOPS_AGENT_API_TOKEN_SHA256": hashlib.sha256(
                self.keys["deployment"].encode()
            ).hexdigest(),
            "BANKOPS_AGENT_APPROVAL_DB_PATH": str(self.out / "approvals.sqlite3"),
            "BANKOPS_AGENT_APPROVAL_PROPOSER_TOKEN_SHA256": hashlib.sha256(
                self.keys["proposer"].encode()
            ).hexdigest(),
            "BANKOPS_AGENT_APPROVAL_REVIEWER_TOKEN_SHA256": hashlib.sha256(
                self.keys["reviewer"].encode()
            ).hexdigest(),
            "BANKOPS_AGENT_LLM_PROVIDER": "disabled",
            "BANKOPS_AGENT_REMEDIATION_ENABLED": "false",
            "BANKOPS_AGENT_AIRFLOW_ENABLED": "false",
            "BANKOPS_AGENT_PROMETHEUS_URL": "http://127.0.0.1:9",
            "BANKOPS_AGENT_JAEGER_URL": "http://127.0.0.1:9",
        }
        self.start(
            "agent-service", [str(PYTHON), "-m", "bankops_agent.main"], ROOT / "agent", agent
        )
        self.ready(18067, "/health")
        proxy = {
            "BANKOPS_BANKING_API_TARGET": "http://127.0.0.1:18066",
            "BANKOPS_AGENT_API_TOKEN": self.keys["deployment"],
        }
        for name in ("MONITORING", "INVESTIGATION", "GOVERNANCE", "RECONCILIATION"):
            proxy["BANKOPS_" + name + "_API_TARGET"] = "http://127.0.0.1:18067"
        self.start(
            "vite",
            [
                shutil.which("node") or "node",
                "node_modules/vite/bin/vite.js",
                "--host",
                "127.0.0.1",
                "--port",
                "5196",
                "--strictPort",
            ],
            FRONT,
            proxy,
        )
        self.ready(5196, "/")
        session = {k: self.keys[k] for k in ("operator", "deployment", "proposer", "reviewer")}
        self.command(
            "live-chromium",
            [
                shutil.which("npx.cmd") or "npx",
                "playwright",
                "test",
                "--config",
                "playwright.security.config.ts",
            ],
            cwd=FRONT,
            env={
                "BANKOPS_SECURITY_E2E": "step66-isolated",
                "BANKOPS_SECURITY_SESSION": json.dumps(session),
                "BANKOPS_SECURITY_LOG_DIR": str(self.out),
            },
        )
        token = self.api_checks()
        result = self.tooling(
            "database-security-and-reconciliation",
            "security/database_checks.py",
            extra={"BANKOPS_SECURITY_EXPIRE_HASH": hashlib.sha256(token.encode()).hexdigest()},
        )
        self.report["database_evidence"] = json.loads(result)
        assert http(18066, "/api/v1/customer/me", token=token)[0] == 401
        self.report["expired_session_denied"] = True

    def api_checks(self):
        base = "/api/v1/customer"

        def identity():
            body = {"username": "probe_" + uuid4().hex, "password": secrets.token_urlsafe(32)}
            assert http(18066, base + "/register", "POST", body=body)[0] == 201
            status, login, _ = http(18066, base + "/login", "POST", body=body)
            assert status == 200
            token = login["token"]
            assert (
                http(
                    18066, base + "/login", "POST", body=body | {"password": "incorrect-password"}
                )[0]
                == 401
            )
            status, account, headers = http(18066, base + "/accounts", "POST", token, {})
            assert (
                status == 201
                and "no-store" in headers.get("Cache-Control", "")
                and "Set-Cookie" not in headers
            )
            return token, account["id"]

        a, source = identity()
        b, destination = identity()
        assert (
            http(
                18066,
                f"/api/v1/dev/accounts/{source}/fund",
                "POST",
                self.keys["operator"],
                {"amount": 100},
                str(uuid4()),
            )[0]
            == 201
        )
        body = {"sourceAccountId": source, "destinationAccountId": destination, "amount": 10}
        key = str(uuid4())
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(http, 18066, base + "/transfers", "POST", a, body, key)
                for _ in range(2)
            ]
            results = [f.result() for f in futures]
        assert {r[0] for r in results} == {200, 201}
        assert results[0][1]["id"] == results[1][1]["id"]
        assert http(18066, base + "/transfers", "POST", a, body | {"amount": 11}, key)[0] == 409
        assert http(18066, base + "/transfers", "POST", b, body, str(uuid4()))[0] == 404
        assert (
            http(18066, base + "/transfers", "POST", a, body | {"amount": 10000}, str(uuid4()))[0]
            == 422
        )
        for path in (
            f"/accounts/{source}",
            f"/accounts/{source}/transactions",
            "/transfers/" + results[0][1]["id"],
        ):
            assert http(18066, base + path, token=b)[0] == 404
        assert http(18066, "/api/v1/operator/me", token=a)[0] == 401
        for invalid in (None, "malformed", "cus_" + "x" * 43, self.keys["operator"]):
            assert http(18066, base + "/me", token=invalid)[0] == 401
        assert http(18067, "/evidence/prometheus")[0] == 401
        assert http(18067, "/evidence/prometheus", token=self.keys["deployment"])[0] == 200
        self.report["api_checks"] = {
            "concurrent_idempotency": True,
            "idor_denied": True,
            "cross_customer_debit_denied": True,
            "insufficient_funds_rejected": True,
            "customer_operator_separation": True,
            "malformed_credentials_denied": True,
        }
        return a

    def close(self):
        for child in reversed(self.children):
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)
        for log in self.logs:
            log.close()
        for name in self.containers:
            result = subprocess.run(["docker", "stop", name], capture_output=True, timeout=30)
            if result.returncode:
                self.report["status"] = "FAIL"
                self.report.setdefault("cleanup_failed", []).append(name)
        for path in self.out.glob("*.log"):
            text = path.read_text(encoding="utf-8", errors="replace")
            leaked = any(secret in text for secret in self.keys.values())
            if leaked:
                for secret in self.keys.values():
                    text = text.replace(secret, "[REDACTED]")
                path.write_text(text, encoding="utf-8")
                self.report["status"] = "FAIL"
                self.report["privacy_failure"] = True
        self.report["migrations_unchanged"] = self.before == hashes()
        if not self.report["migrations_unchanged"]:
            self.report["status"] = "FAIL"
        self.report["test_containers_stopped"] = self.containers
        (self.out / "report.json").write_text(json.dumps(self.report, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--isolated", action="store_true", required=True)
    parser.add_argument("--regressions", action="store_true")
    options = parser.parse_args()
    # Fail before creating anything if these dedicated ports are already occupied.
    for port in (55466, 55467, 18066, 18067, 18068, 5196):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))
    harness = Harness()
    try:
        if options.regressions:
            harness.regressions()
        harness.integration()
        harness.report["status"] = "PASS"
    except Exception as error:
        harness.report["status"] = "FAIL"
        harness.report["failed_stage"] = (
            str(error) if isinstance(error, VerificationError) else type(error).__name__
        )
    finally:
        harness.close()
    print(
        json.dumps(
            {
                "status": harness.report["status"],
                "report": str(harness.out.relative_to(ROOT) / "report.json"),
            }
        ),
        flush=True,
    )
    raise SystemExit(0 if harness.report["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
