# BankOps AI reliability agent foundation

Independent FastAPI service for **Python 3.12**. `GET /health` returns HTTP 200:

```json
{"status":"ok","service":"bankops-reliability-agent"}
```

This is process health, with no external dependency probes. `GET /evidence/prometheus`
explicitly collects read-only aggregate evidence; see [PROMETHEUS_EVIDENCE.md](PROMETHEUS_EVIDENCE.md).
`GET /incidents/detect` applies deterministic rules to a fresh evidence snapshot;
see [INCIDENT_DETECTION.md](INCIDENT_DETECTION.md) for thresholds and state semantics.
`GET /evidence/traces` collects recent, sanitized banking trace evidence from
Jaeger; see [TRACE_EVIDENCE.md](TRACE_EVIDENCE.md) for limits and privacy rules.
`GET /evidence/logs` reads bounded, allowlisted WARN/ERROR evidence from an
explicitly configured local JSONL file; see [LOG_EVIDENCE.md](LOG_EVIDENCE.md).
`GET /incidents/investigate` combines detection and supporting evidence in one
read-only report; see [INVESTIGATION.md](INVESTIGATION.md) for its response contract.
`POST /workflows/investigate` runs the same investigation through a deterministic
LangGraph workflow with optional, validated LLM hypothesis analysis; see
[WORKFLOW.md](WORKFLOW.md) and [RCA.md](RCA.md). Inference is disabled by default.
RCA supports a JSON gateway or an OpenAI-compatible chat-completion endpoint;
endpoint, model and credentials are supplied through environment variables.
The disabled Groq profile and exactly two opt-in synthetic scenarios are described
in [GROQ.md](GROQ.md).
Human-held reviewer approval and persistent proposal records are described in
[APPROVALS.md](APPROVALS.md). Approval never executes remediation.
Actual isolated HTTP/process-restart verification is documented in
[APPROVAL_VERIFICATION.md](APPROVAL_VERIFICATION.md).
The disabled-by-default, approved read-only execution framework is documented in
[REMEDIATION.md](REMEDIATION.md).
Actual read-only action, failure and restart results are recorded in
[REMEDIATION_VERIFICATION.md](REMEDIATION_VERIFICATION.md).
Run synthetic or opt-in live checks using
[LIVE_RCA_VERIFICATION.md](LIVE_RCA_VERIFICATION.md).
Local Ollama readiness and disabled environment preparation are documented in
[OLLAMA_SETUP.md](OLLAMA_SETUP.md); no model is downloaded automatically.
API docs and OpenAPI
routes are disabled. There are no banking API/database clients,
background jobs or infrastructure-changing remediation actions.

## Run locally

From the repository root in PowerShell:

```powershell
py -3.12 -m venv agent/.venv
cd agent
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
.\.venv\Scripts\bankops-agent.exe
```

In another shell:

```powershell
$id = [guid]::NewGuid().ToString()
Invoke-WebRequest http://localhost:8000/health -Headers @{'X-Correlation-ID'=$id}
```

Use the `bankops-agent` entry point so server logging is configured safely.
The application factory is `bankops_agent.app.create_app`; its outer ASGI wrapper
also adds correlation IDs to framework-generated error responses.

## Environment configuration

| Variable | Default | Valid values |
| --- | --- | --- |
| `BANKOPS_AGENT_ENVIRONMENT` | `dev` | `dev`, `test`, `production` |
| `BANKOPS_AGENT_HOST` | `127.0.0.1` | IPv4/IPv6 literal |
| `BANKOPS_AGENT_PORT` | `8000` | 1–65535 |
| `BANKOPS_AGENT_LOG_LEVEL` | `INFO` | DEBUG, INFO, WARNING, ERROR, CRITICAL |
| `BANKOPS_AGENT_PROMETHEUS_URL` | `http://localhost:9090` | HTTP(S) base URL, without credentials/query/fragment |
| `BANKOPS_AGENT_PROMETHEUS_TIMEOUT_SECONDS` | `5` | Positive finite seconds, at most 30 |

Invalid settings fail startup. Values come from the process environment; `.env`
is deliberately not loaded automatically, and banking credentials/settings are
not read. `.env.example` documents the agent namespace. Environment selection
does not activate future capabilities.

## JSON logging

HTTP events include UTC `timestamp`, `level`, constant `service` and `logger`,
bounded `message`/`event_type`, `http_status`, and `correlation_id`.
`X-Correlation-ID` accepts a single UUID (normalized to lowercase); missing,
invalid or duplicate values generate a UUID. The value is returned in response
headers. Context variables are restored after success, errors and concurrent
requests. Startup events have a null correlation ID.

Logs do not render request paths, queries, bodies, headers, exception details,
credentials or arbitrary log messages/extras. Uvicorn access/exception diagnostics
are suppressed by the entry point. Logging sink failures do not change responses.
At WARNING or above, informational request/startup events are suppressed.

```powershell
.\.venv\Scripts\bankops-agent.exe > agent.log
Get-Content agent.log | ForEach-Object { $_ | ConvertFrom-Json } |
    Where-Object correlation_id -eq $id
```

## Modules

- `api/`: health and read-only evidence HTTP contracts.
- `config.py`, `logging.py`, `middleware.py`: settings and request observability.
- `detection/`: deterministic incident detection rules.
- `evidence/`: privacy-bounded Prometheus and Jaeger evidence collection.
- `rca/`: future root cause analysis boundary.
- `remediation/`: future remediation boundary.

The RCA and remediation packages contain documentation only, with no operational
behavior or invented interfaces to commit future implementations to.

## Dependencies and tests

`pyproject.toml` declares runtime and test dependencies. `requirements.lock` pins
runtime dependencies; `requirements-test.lock` pins the runtime plus test tools.
Regenerate with Python 3.12 and pip-tools:

```powershell
.\.venv\Scripts\python.exe -m pip install 'pip-tools>=7,<8'
.\.venv\Scripts\python.exe -m piptools compile --strip-extras pyproject.toml -o requirements.lock
.\.venv\Scripts\python.exe -m piptools compile --strip-extras --extra test -c requirements.lock pyproject.toml -o requirements-test.lock
.\.venv\Scripts\python.exe -m pip install -r requirements-test.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
.\.venv\Scripts\python.exe -m pytest
```

Tests cover health, validated/namespaced settings,
correlation IDs, JSON field safety, error responses, concurrency, and failed log
handlers, plus mocked Prometheus responses and real HTTP against a local fake
Prometheus server. No database or running BankOps services are required.

## Docker

```powershell
docker build -t bankops-agent:dev agent
docker run --rm -p 127.0.0.1:8000:8000 bankops-agent:dev
```

The Python 3.12 image runs as a non-root user and includes a local health check.
The container binds internally to `0.0.0.0`; publish its host port on loopback.
No Compose or monitoring services are changed. Runtime uses the pinned lock;
test tools are not installed in the image.

## Verification — October 15, 2026

Step 50: **421 agent tests passed**, with warnings treated as errors, plus
**202 banking tests passed** against disposable PostgreSQL. Both actions,
failures, actual process restarts and no-retry guarantees passed against local
HTTP evidence fixtures. Development banking fingerprints were unchanged. See
[REMEDIATION_VERIFICATION.md](REMEDIATION_VERIFICATION.md).

Step 49: **420 agent tests passed**, with warnings treated as errors, plus
**202 banking tests passed** against disposable PostgreSQL. Execution tests use
isolated SQLite and mocked evidence collectors. See [REMEDIATION.md](REMEDIATION.md)
for approval binding, at-most-once claims, read-only actions and failure limits.

Step 48: **395 agent tests passed**, with warnings treated as errors, plus
**202 banking tests passed** against disposable PostgreSQL. Real loopback HTTP,
service-process restarts and concurrent decisions passed; development banking
table content fingerprints were unchanged. See
[APPROVAL_VERIFICATION.md](APPROVAL_VERIFICATION.md).

Step 47: **394 agent tests passed**, with warnings treated as errors, plus
**202 banking tests passed** against disposable PostgreSQL. Approval tests use
isolated SQLite storage. See [APPROVALS.md](APPROVALS.md) for authentication,
state transitions and audit guarantees. No remediation is executed.

Step 45: **362 agent tests passed**, with warnings treated as errors, plus
**202 banking tests passed** against disposable PostgreSQL. Both prepared Groq
scenarios passed with mocked responses; no live inference was executed. See
[GROQ.md](GROQ.md) for secure configuration and the hard two-request opt-in cap.

Step 43: **345 agent tests passed**, with warnings treated as errors, plus
**202 banking tests passed** against disposable PostgreSQL. New provider tests
are mocked; no live or paid API calls were made. See [RCA.md](RCA.md) for the
required OpenAI-compatible endpoint/model/key configuration.

Step 42: **300 agent tests passed**, with warnings treated as errors, plus
**202 banking tests passed** against disposable PostgreSQL. All eleven synthetic
verification scenarios passed. Real provider verification is blocked by missing
gateway configuration and explicit opt-in; no real inference was sent. See
[LIVE_RCA_VERIFICATION.md](LIVE_RCA_VERIFICATION.md).

Step 41: **277 agent tests passed**, with warnings treated as errors, plus
**202 banking tests passed** against disposable PostgreSQL. See [RCA.md](RCA.md)
for configuration, validation, privacy and limitations. Provider tests are mocked;
no live LLM was contacted.

Step 40: **227 agent tests passed**, with warnings treated as errors, plus
**202 banking tests passed** against disposable PostgreSQL. See
[WORKFLOW.md](WORKFLOW.md) for architecture and execution.

Step 39: **208 agent tests passed**, with warnings treated as errors, plus
**202 banking tests passed** against disposable PostgreSQL. See
[INVESTIGATION.md](INVESTIGATION.md) for the unified report contract.

Step 38: **194 tests passed**, with warnings treated as errors, including local
JSONL and HTTP integration tests for privacy, source restrictions, and failures.
See [LOG_EVIDENCE.md](LOG_EVIDENCE.md).

Step 37: **156 tests passed**, with warnings treated as errors, including mocked
and real HTTP integration tests for the trace collector. See
[TRACE_EVIDENCE.md](TRACE_EVIDENCE.md).

Step 36: **118 tests passed**, with warnings treated as errors, including every
detection rule and its read-only HTTP integration. See
[the incident detection guide](INCIDENT_DETECTION.md).

Step 35: **61 tests passed**, with warnings treated as errors; fixed aggregate
queries also ran read-only against development Prometheus. See
[the evidence verification report](PROMETHEUS_EVIDENCE.md#verification).
The following records the earlier foundation verification:

- Python 3.12 unit suite: **23 passed**, with warnings treated as errors.
- Dependency validation: `pip check` reported no broken requirements.
- Final Docker image built successfully. An isolated smoke container ran on
  Python **3.12.15**, as UID **10001**, with external networking disabled.
- `/health` returned HTTP **200** and the documented JSON body. The supplied
  correlation UUID matched its response header and structured JSON request event.
- Docker health status was **healthy**. The temporary container was removed.
- All changes are confined to `agent/`. No banking, migration, Compose or
  monitoring-service files were changed; no banking APIs or databases were contacted.

Step 51 adds immutable, recorded-outcome verification: [POST_REMEDIATION_VERIFICATION.md](POST_REMEDIATION_VERIFICATION.md).

Step 52 lifecycle, fault-boundary and audit verification: [RELIABILITY_VERIFICATION.md](RELIABILITY_VERIFICATION.md).

Step 56 adds opt-in, authenticated Airflow reconciliation evidence and deterministic incidents: [AIRFLOW_EVIDENCE.md](AIRFLOW_EVIDENCE.md).
