# Unified local platform

## Current quick start

From the repository root with Python 3.12, local Docker Desktop/Engine and
Docker Compose 2.24.4+:

```powershell
python local/platform.py up
python local/platform.py health
python local/platform.py logs banking
python local/platform.py verify
python local/platform.py stop
python local/platform.py up
python local/platform.py restart frontend
python local/platform.py test
```

First `up` creates private credentials, builds only missing images and waits for
all nine runtimes plus successful prepare/migrate/grant jobs. Available images
are never rebuilt automatically; use `build <service>` after source changes.
For existing Steps 67–68 installations run `python local/platform.py build frontend`
once, then `up`, to adopt the shutdown fix. Cold Airflow readiness can take minutes;
the launcher emits waiting messages and actionable redacted error tails.

`stop` preserves every container, network and volume. `restart` without service
names performs a full health-gated stop/start; named restarts affect only those
runtime services. `health` exits nonzero for unhealthy/missing services or failed
migration/ACL jobs. Logs show the last 100 lines, redacted before display/storage.
Private launcher logs live in `local/results` as `startup.log`, `build.log`,
`stop.log`, `restart.log` and `tests.log`.

### Service access and demo

| Interface | URL | Local authentication |
| --- | --- | --- |
| React | http://127.0.0.1:15173 | Explicit operator/reviewer credential |
| Airflow | http://127.0.0.1:18087 | `localadmin` or `agentviewer` |
| Prometheus | http://127.0.0.1:19097 | Localhost interface |
| Grafana | http://127.0.0.1:13007 | `admin` |
| Jaeger | http://127.0.0.1:16687 | Localhost interface |

Open ignored `local/.env.local` in a local editor to retrieve credentials. Never
paste secrets, resolved Compose environments or raw inspect environments into
logs/Git. No `VITE_*` credential is used. The launcher strips inherited service,
tracing and Compose overrides from child commands, making its dotenv/project
authoritative. It rejects remote Docker endpoints. Banking, the agent and both
databases remain unpublished; approved frontend routes preserve existing auth.

For a demo, start, check health, open the UIs and run `verify`. The ordinary stack
does not seed/fund accounts or enable customer APIs. Low traffic can correctly
show insufficient evidence. Inference, remediation and the agent's Airflow
connector stay disabled; no paid cloud API or production profile is required.
`verify` needs only Python stdlib + running containers. `test` additionally needs
the agent venv and cached frontend Playwright dependencies.

### Configurable networking and troubleshooting

For NEW networks, the launcher inspects existing Docker IPAM and allocates unused
/24s from 10.69.0.0/16. Choose a different RFC1918 /16 through /24 on initial setup:

```powershell
python local/platform.py --network-pool 10.70.0.0/16 up
```

`BANKOPS_LOCAL_NETWORK_POOL` is the equivalent initial-command option. Review
host/VPN routes separately. Plans persist in ignored `network-plan.local.json`
and `networks.local.json`. Existing declarations are adopted unchanged, with no
new IPAM imposed on them. A saved pool, changed network definition or another
project's network ownership cannot be silently replaced. No existing network or
daemon setting is modified or pruned. The host's automatic pool remains exhausted
for unrelated new projects; explicit IPAM avoids it without destructive cleanup.
Keep the saved plan and credentials with retained volumes.

For failures use `health`, then `logs <service>`; inspect `prepare`, `migrate`,
`grant`, `banking` and `airflow` first. Port/network conflicts and Docker access
errors receive specific guidance. Do not delete/reinitialize volumes, rotate
credentials or bypass migrations as a shortcut. Legacy/root Compose volumes are
never automatically adopted or reassigned.

### Graceful shutdown and verification

The frontend's minimal Node PID 1 supervisor forwards SIGTERM/SIGINT to Vite. It
returns zero only for a matching requested shutdown; startup errors, unsolicited
exits, SIGKILL and other application failures remain failures, including failures
during shutdown. Auth/proxy behavior is unchanged. The Step 68 npm exit-1 finding
below is historical and superseded by the Step 69 results.

```powershell
python local/platform.py test --recovery
python local/check_developer.py
```

These use fresh disposable projects, capacity for a second platform, Node/
Playwright for live Chromium and already-built images. Run recovery suites one
at a time. Built images get fixture-owned local tags with `pull_policy: never`, preventing
unexpected registry pulls or image changes after a tag update. Private state is
in ignored `local/results/step69-<id>` or `step68-<id>`. Fixtures are stopped in
cleanup and all volumes remain. Existing development data/roles are never targets.

The original health/dependency chain and separate migration/runtime identities
remain: prepare -> dedicated Flyway migrate/validate -> grant -> banking.
Migration/admin secrets stay out of application runtimes, Airflow remains SELECT
only on financial evidence and the agent has no financial network/credentials.
V1–V6 and customer/AI/approval/remediation/reconciliation behavior are unchanged.
This remains local preview/auth infrastructure; production TLS/identity/backup
controls, host-power-loss recovery and Linux verification remain outside scope.

## Step 67 — original unified platform runbook

**Recovery testing:** see [Step 68](#step-68--docker-reliability-and-recovery) below.

This independent Compose project creates fresh project-scoped volumes. It never
attaches the root development database or the standalone Airflow volumes.
Requires Docker Compose 2.24.4+ (`!override`), Docker Desktop/Linux Docker, Python
3, and adequate memory for Airflow plus the Java/container builds (8 GB minimum
recommended). These are local development images, not a production deployment.

From the repository root:

```powershell
python local/init.py
docker compose --env-file local/.env.local -f local/compose.yaml config --quiet
docker compose --env-file local/.env.local -f local/compose.yaml build
docker compose --env-file local/.env.local -f local/compose.yaml up -d --wait --wait-timeout 600
docker compose --env-file local/.env.local -f local/compose.yaml ps -a
python local/verify.py
docker compose --env-file local/.env.local -f local/compose.yaml logs --tail 100
docker compose --env-file local/.env.local -f local/compose.yaml stop
```

`stop` preserves containers and every volume. Use the same `up` command to resume.
Do not use volume deletion, prune, or development-volume overrides. Keep the
generated project name and credentials for this volume's lifetime. `init.py`
refuses to overwrite existing credentials. Do not commit/share `config` output,
dotenv files, secret files, or container inspection output containing environments.
Protect `local/.env.local` and `local/.secrets` using your Windows account ACLs
or POSIX file permissions. Local Compose uses environment injection for most
secrets; Docker administrators can inspect those credentials.

| Interface | Local URL |
| --- | --- |
| React workspace | http://127.0.0.1:15173 |
| Airflow | http://127.0.0.1:18087 |
| Prometheus | http://127.0.0.1:19097 |
| Grafana | http://127.0.0.1:13007 |
| Jaeger | http://127.0.0.1:16687 |

Banking, agent, both databases and OTLP have no published ports. Browser calls use
the existing approved Vite proxies. Operator routes require the generated banking
token supplied by the operator; no operator credential is injected. Customer APIs
remain disabled. Proposer/reviewer tokens are distinct and retain the existing
approval permissions; inference, remediation, and agent-triggered Airflow access
remain disabled. Airflow UI users are `localadmin` and `agentviewer`; Grafana uses
`admin`. Their passwords are in the ignored generated file.

The financial network is internal and accessible only to PostgreSQL, banking,
and SELECT-only Airflow. Metadata has its own internal network. The agent uses
HTTP evidence on the telemetry network and its own approval SQLite volume; it
receives no banking DB credentials or Docker socket. Airflow DAGs start paused.
The existing patched Airflow image, metadata initializer, Grafana provisioning,
HBA policy, provisioning functions and Flyway launcher are reused.

Startup is health-gated PostgreSQL → prepare → dedicated migrate/validate →
grant → banking → Prometheus → agent/frontend/Grafana. One-shot tools share the
PostgreSQL network namespace to use the existing loopback-only migration checks.
The host provisioning CLI and migration target safeguards remain unchanged.
Migration/admin credentials never enter application runtimes. Repeat startup
validates Flyway checksums; clean is disabled. V1–V6 remain unchanged.

Verification commands:

```powershell
python local/verify.py
python local/regressions.py
agent/.venv/Scripts/python.exe -m pytest security/tests -q -W error
cd agent
.venv/Scripts/python.exe -m pytest tests -q -W error
cd ../frontend
npm test
npm run lint
npm run typecheck
```

The pre-existing Airflow test image is built using `airflow/Dockerfile.test`.
`regressions.py` starts a separate PostgreSQL 17 test project on loopback:15567,
runs Airflow/database and Maven suites, and stops the fixture without deleting
its volume. It requires local Java 21+, the Maven wrapper and cached/downloadable
dependencies (Windows defaults to JDK 25; set JAVA_HOME elsewhere). Never point
corrupt-fixture tests at retained application volumes or development banking.
`verify.py` performs read-only HTTP checks and a
rolled-back ACL denial probe, checks the real reconciliation module and financial
snapshot, and records redacted results under ignored `local/results`.

See the actual run results below for verified scope and remaining limitations.

## Actual results — 2026-10-28 (America/Chicago)

Verified on Windows + Docker Desktop, Compose 2.39.4, project
`bankops-step67-4c201966c1cb`. All nine runtime containers are healthy and remain
running. The three one-shot ACL/migration jobs exited 0. The separate regression
PostgreSQL fixture was stopped, retaining its volume. Unrelated containers stayed
running. No development database, role or persistent volume was modified.

| Check | Result |
| --- | --- |
| Final Compose configuration validation | Passed |
| All service images, including patched Airflow and Jaeger probe | Built |
| Whole-stack `up --wait` | Passed; nine healthy runtime containers |
| Prepare → dedicated Flyway → grant, including repeat startup | Exit 0; migrate/validate succeeded |
| Frontend approved banking and reliability routes | Passed; operator required; cross-origin denied; dev funding blocked; customer API disabled |
| Prometheus authenticated banking scrape | Target UP |
| Grafana provisioned Prometheus datasource | Health OK |
| Jaeger and actual agent trace collector | Status ok; 10 banking traces collected |
| Airflow API/scheduler/DAG processor/metadata health | Healthy |
| Actual `bankops_daily_reconciliation` DAG via `airflow dags test` | All four tasks succeeded; DAG run success |
| Airflow real SELECT-only connection and reconciliation module | PASS; write denied even with read-write transaction; financial snapshot unchanged |
| Banking regressions on separate disposable PostgreSQL | 219 passed; zero failures/errors/skips |
| Agent regressions | 487 passed |
| Airflow/database regressions on separate disposable PostgreSQL | 57 passed |
| Frontend component/API regressions | 104 passed |
| Security harness regressions | 7 passed |
| Frontend lint and TypeScript | Passed |
| Secret/volume isolation | Generated dotenv, secret files and reports ignored; no external volumes; no banking secrets/network for agent |

These are 874 regression cases plus explicit live HTTP/SQL/DAG checks. Redacted
verification output, build logs and suite results are in ignored `local/results`.
The live stack's initial ledger is empty; populated transactions and financial
invariants were tested in the separate regression cluster. V1–V6 were untouched.
During implementation, startup exposed missing UI port bindings on internal-only
networks, non-root Vite temp-directory permissions and the obsolete Jaeger v1
services probe. Those were corrected and final startup/verification passed.
Initial Python invocations also exposed a missing host psycopg dependency, a
working-directory-sensitive agent test, and a missing disposable Airflow fixture;
the documented isolated commands correct those invocation issues, without
weakening any assertions.

## Limits and remaining work

This configuration deliberately keeps customer APIs, inference and remediation
disabled. Agent Airflow evidence ingestion remains disabled because its existing
connector requires HTTPS outside loopback and a separately issued viewer token;
no connector transport restriction was weakened. Airflow itself and its real DAG
were verified directly. Approval storage persists, with distinct proposer/reviewer
credentials and unchanged authorization logic; no automatic approval is enabled.

The root infrastructure stack and existing development volumes are intentionally
left on their earlier configuration. Migrating those volumes requires the backup,
restore and ownership handoff described in `database/README.md`. Scheduled DAG
execution remains paused; only the explicit local DAG test was run. No full
Chromium end-to-end suite or new dependency/OS vulnerability audit was run in
Step 67. Existing transaction/auth/approval regressions passed.

Builds need public package/image downloads or a populated cache; versioned image
tags are used rather than immutable digest locks. Linux portability is designed
but was not executed here (the test fixture uses Docker Desktop's
`host.docker.internal`; Linux needs the equivalent host-gateway mapping). Jaeger
uses its default in-memory trace storage, so trace evidence is ephemeral across
restarts. The BusyBox readiness executable comes from the same pinned Prometheus
image already used by this stack. Local cleartext Docker networking, environment
secrets, local Airflow auth and Vite preview are not production controls. Production
still needs TLS, managed identity/secrets, image digest/OS auditing, backup/restore
verification and deployment review. No paid external API or cloud deployment ran.

## Step 68 — Docker reliability and recovery

Run from the repository root after the Step 67 images have been built:

```powershell
docker compose --env-file local/.env.local -f local/compose.yaml config --quiet
docker compose --env-file local/.env.local -f local/compose.yaml build
agent/.venv/Scripts/python.exe -m pytest local/tests security/tests -q -W error
agent/.venv/Scripts/python.exe local/recovery.py
```

`recovery.py` creates a new random `bankops-step68-*` project with unique
credentials and fresh named volumes on every invocation. It reuses the built
images, resolves the unified Compose configuration, and saves its private fixture
manifest under ignored `local/results/step68-*/compose.json`. It refuses external
volumes/networks, writable host mounts, public binds, infrastructure credentials
in applications and agent financial access. The running Step 67 project and all
development databases remain untouched. Do not publish the manifest: it contains
local synthetic credentials. Failed runs are stopped; volumes are never deleted.
Repeated preserved projects exhausted Docker's default automatic subnet pool
during verification. The harness now inspects existing networks and allocates
non-overlapping /24 test subnets from 10.68.0.0/16 explicitly. It fails if that
range is exhausted and never removes networks to make room. Docker host/none
networks can have null IPAM metadata; those are handled separately from bridge
subnets. The test range must also suit the host/VPN routing environment.
The host's default pool remains exhausted for other **new** projects until a
separate reviewed IPAM or network-management change is made. Existing projects
continue using their current networks. No daemon-wide network configuration was
changed and no retained network was removed.

The disposable fixture alone enables the existing `dev,db-secure` reserve
bootstrap and shortens Hikari's connection-acquisition timeout to two seconds.
It uses authenticated APIs to create two accounts, fund one from a finite $10,000
synthetic reserve and transfer $250. Customer APIs, inference, remediation and
agent-triggered Airflow access remain disabled. No SQL trigger is bypassed and
no Flyway migration is edited. The ordinary local stack retains its existing
profiles and disabled bootstrap.

The harness tests an intentional unhealthy-PostgreSQL startup barrier and actual
prepare/migrate/grant timing; then all nine runtime containers must become
healthy. It interrupts PostgreSQL, banking, Prometheus and the agent, restarts
Grafana/Jaeger/Airflow, and performs a full graceful stop/start. A persistent real
Chromium session observes loading, outage and recovery states. Browser traces,
screenshots and videos are disabled; credentials travel over stdin and remain in
memory. It compares complete financial snapshots and Flyway history checksums,
uses the same transfer idempotency key after recovery, runs real reconciliation
DAGs, and checks named volume identities plus markers in all seven declared
persistent volumes. The fixture is stopped in `finally`, preserving its volumes.

### Recovery procedures for the retained local platform

These commands deliberately target the ordinary local project, so use them only
when you intend to recover that project. The automated fault tests never do so.

```powershell
# Inspect current status before taking action.
docker compose --env-file local/.env.local -f local/compose.yaml ps -a
docker compose --env-file local/.env.local -f local/compose.yaml logs --tail 100 banking postgres

# Resume PostgreSQL, then inspect banking readiness and authenticated reads.
docker compose --env-file local/.env.local -f local/compose.yaml start postgres
docker compose --env-file local/.env.local -f local/compose.yaml ps

# Recover a stopped evidence service; inspect health before trusting its data.
docker compose --env-file local/.env.local -f local/compose.yaml start prometheus agent
docker compose --env-file local/.env.local -f local/compose.yaml restart grafana jaeger
docker compose --env-file local/.env.local -f local/compose.yaml restart airflow

# Graceful stop/resume with persisted volumes and checked migration sequencing.
docker compose --env-file local/.env.local -f local/compose.yaml stop --timeout 30
docker compose --env-file local/.env.local -f local/compose.yaml up -d --wait --wait-timeout 600
agent/.venv/Scripts/python.exe local/verify.py
```

Startup dependencies do not continuously restart dependent services or cascade
outages. A healthy agent process does not establish banking or evidence health.
Wait for a fresh successful Prometheus scrape and query the relevant APIs.
Monitoring may correctly show insufficient data after recovery because traffic
is low or a five-minute rate window has gaps. Refresh account/history reads after
banking recovers. Do not automatically resubmit financial writes: resolve an
uncertain outcome by reading transfer/history and, only for an explicit retry,
retain the original request and idempotency key. Never generate a new key merely
because a connection failed. Do not reinitialize, reset passwords or delete
volumes as a recovery shortcut.

### Troubleshooting

```powershell
docker compose --env-file local/.env.local -f local/compose.yaml logs --tail 100 postgres banking agent
docker compose --env-file local/.env.local -f local/compose.yaml logs --tail 100 prometheus grafana jaeger
docker compose --env-file local/.env.local -f local/compose.yaml logs --tail 100 airflow airflow-metadata
docker compose --env-file local/.env.local -f local/compose.yaml logs --tail 100 prepare migrate grant
docker compose --env-file local/.env.local -f local/compose.yaml exec -T banking curl -fsS http://127.0.0.1:8080/actuator/health
docker compose --env-file local/.env.local -f local/compose.yaml exec -T prometheus wget -q -O - http://127.0.0.1:9090/-/ready
docker compose --env-file local/.env.local -f local/compose.yaml exec -T jaeger /busybox wget -q -O - http://127.0.0.1:16686/api/v3/services
```

For a stopped recovery fixture, select the **exact** generated manifest named in
its `report.json`, inspect `docker compose -f <manifest> ps -a`, and read its
redacted `startup.log`, `dag-before.log`, `dag-after.log` and stop logs. Do not use
a development project's name to resume a fault test. Ports 15268, 18068, 19068,
13068 and 16668 must be free. Run recovery tests one at a time. Give Docker enough
memory for two full stacks and avoid overlapping Java/Chromium/frontend suites
on constrained machines. The fixture's intentional `/tmp/step68-ready` health
barrier is opened by the harness; it is not part of the normal local health check.

Regression commands used for Step 68 (run heavy suites sequentially):

```powershell
agent/.venv/Scripts/python.exe local/regressions.py
agent/.venv/Scripts/python.exe -m pytest local/tests security/tests -q -W error
cd agent
.venv/Scripts/python.exe -m pytest tests -q -W error
cd ../frontend
npm test -- --maxWorkers=1
npm run lint
npm run typecheck
npm run test:e2e
```

### Recovery scope and limitations

Docker health status can lag a failed dependency because of retry thresholds.
The harness also waits for successful authenticated reads and bounded explicit
replays of the same completed transfer, without restarting banking. The replay
probe accepts only temporary 500/503 responses until the original transfer is
returned; a new transfer ID, unexpected HTTP status, deadline or changed snapshot
fails the test. This is an isolated test probe, not a new automatic financial
retry policy in the application. A Prometheus scrape succeeding only proves
the metrics endpoint is reachable, not that a financial transaction can commit.

These are controlled service stops/restarts on one Docker Desktop host. They
do not simulate host power loss, disk corruption, lost volumes, network partitions
or a process killed at the exact database commit boundary. The tested transfer
was already committed before interruption. Restoring a backup and recovering
arbitrary in-flight requests require separate verification. Jaeger memory traces
are intentionally lost on restart; the check requires newly exported traces
after restart. The financial database, Airflow metadata/auth/logs, agent approval
volume, Prometheus and Grafana volume markers must persist. Scheduled DAGs stay
paused; explicit before/after DAG tests and scheduler health are checked.
Agent Airflow ingestion remains disabled under its existing HTTPS restriction.
Windows Docker Desktop was exercised; other operating systems were not.

### Actual Step 68 results — 2026-10-28 (America/Chicago)

The final complete run is `local/results/step68-f02259012af3/report.json`, project
`bankops-step68-21da338dc9d9`. Its status is **PASS**, with all **13 recovery
checkpoints** passed. The fixture is stopped and every volume is preserved.
The retained Step 67 project still has all nine runtime containers healthy;
its separate read-only verifier also passed during fault testing.

| Check | Actual result |
| --- | --- |
| Unified Compose validation and image builds | Passed; cached/rebuilt images verified before fault tests |
| Fresh startup and ordering | Nine healthy runtimes; deliberate DB health barrier blocked dependents; prepare/migrate/grant completion order verified |
| Temporary PostgreSQL outage | API unavailable during outage; authenticated reads and same-key transfer replay recovered with banking's original process still running |
| Transfer recovery | Replay returned 200 with original transfer ID; replay probe took 1.25 seconds after read readiness in the final run (not an RTO benchmark) |
| Banking outage | Agent process stayed responsive, fresh scrape evidence reported banking down, Chromium showed error/unavailable states and recovered |
| Prometheus outage | Agent returned unavailable evidence and insufficient-data evaluation; Chromium showed Unavailable; fresh scrape evidence recovered |
| Agent restart | Chromium showed Unavailable, then responding/fresh evidence after restart |
| Grafana restart | Healthy; authenticated provisioned Prometheus datasource check returned OK |
| Jaeger restart | Healthy; actual agent collector received newly exported banking traces |
| Airflow restart | Scheduler/API/DAG processor/metadata healthy; actual reconciliation DAG succeeded both before and after restart |
| Reconciliation and data | PASS throughout successful snapshots; identical financial digest and Flyway history before/after interruptions and full restart |
| Graceful stop and full restart | All nine stopped without exit 137/SIGKILL; full `up --wait` restored all nine to healthy |
| Persistent volumes | Same volume identities and markers in all seven declared volumes survived stop/start |
| No duplicate financial effects | Exactly 3 synthetic accounts, 2 transfers (funding + transfer), 4 ledger postings throughout; original transfer ID retained |
| Authentication and disabled functionality | Anonymous operator denied; customer API disabled before/after; inference/remediation/agent Airflow ingestion stayed disabled |
| V1–V6 | Hashes unchanged |

| Regression suite | Passed |
| --- | ---: |
| Banking, including financial/authentication/ACL integration | 219 |
| Agent | 487 |
| Airflow/database, including actual PostgreSQL SCRAM login/wrong-password integration | 58 |
| Frontend components/API | 104 |
| Desktop/mobile Chromium regression cases | 32 |
| New recovery harness safeguards and Chromium-worker lifecycle | 21 |
| Existing security harness safeguards | 7 |
| **Total** | **928** |

Frontend lint, TypeScript and the Chromium worker syntax check passed. Live
interruption UI checks used headless desktop Chromium; desktop/mobile regression
cases used the existing synthetic route fixtures. Banking/Airflow/database
regressions used their separate disposable PostgreSQL cluster, which is stopped.

Observed shutdown statuses were 0 for agent, PostgreSQL, metadata PostgreSQL,
Prometheus, Grafana and Jaeger; 143 for banking and Airflow; and **1 for the
frontend's existing npm preview wrapper**. The frontend stopped without SIGKILL
and became healthy after restart. The automated graceful-stop assertion checks
bounded completion, stopped state and absence of forced kill; it does not require
all wrappers to return zero. Cleaner frontend PID 1/exit-status handling remains
an operational improvement, not a verified zero-exit guarantee.

Initial attempts exposed malformed synthetic fixture requests (required account
number and forbidden transfer currency field), the need to wait for actual API
recovery beyond Docker health, exhausted default network pools/null IPAM metadata,
and a Chromium worker input pipe preventing process exit. Fixture requests and
bounded readiness checks were corrected; explicit subnet allocation and worker
shutdown fixes have regression coverage. A concurrently run frontend component
suite initially failed two cases; all 104 passed when rerun with one worker and
no frontend application change. Failed disposable projects were stopped and
preserved; none of their partial checks are counted as a successful complete run.

No existing development banking data, roles or volumes were modified or deleted.
No production deployment, paid inference, Docker daemon network reconfiguration
or destructive cleanup was performed. Reports contain aggregate counts/digests;
private manifests and credentials remain ignored local artifacts.
