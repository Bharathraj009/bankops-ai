# Reconlith engineering decisions

These decisions describe the checked-in implementation and its failure boundaries.
Alternatives below explain tradeoffs; they are not claims that every alternative
was prototyped. Results and dates are indexed in [verification evidence](VERIFICATION_EVIDENCE.md).

## Java 21 and Spring Boot banking API

**Problem:** banking writes need validated HTTP contracts, authorization and one
transaction boundary around transfer state, ledger postings and balances.

**Choice:** the [Java 21/Spring Boot build](../backend/banking-service/pom.xml)
provides the framework used by the
[transfer controller](../backend/banking-service/src/main/java/com/bankops/banking/transfer/TransferController.java)
and transactional service. JDBC keeps locking and ledger SQL visible rather than
hiding these operations behind object persistence conventions.

**Tradeoff:** a separate JVM service adds build/runtime overhead compared with
putting banking writes in the Python agent. That separation makes the financial
write boundary explicit. This explains the current design's fit; it does not
assert that another language or framework was benchmarked and rejected.

**Boundary and tests:** Spring transactions alone do not enforce all financial
invariants; database constraints and authorization remain necessary. See
[HTTP transfer tests](../backend/banking-service/src/test/java/com/bankops/banking/TransferApiIntegrationTests.java)
and [API security tests](../backend/banking-service/src/test/java/com/bankops/banking/ApiSecurityFilterTests.java).

## PostgreSQL integrity and idempotency

**Problem:** retries and concurrent transfers must not create duplicate postings or
leave balances and ledger entries inconsistent.

**Choice:** [TransferService](../backend/banking-service/src/main/java/com/bankops/banking/transfer/TransferService.java)
uses a transaction, locks accounts, claims a scoped idempotency key with a canonical
request fingerprint, and completes the transfer without reposting terminal work.
[TransferRepository](../backend/banking-service/src/main/java/com/bankops/banking/transfer/TransferRepository.java)
contains the SQL operations. Accounts are locked in UUID order before claiming
idempotency to reduce lock-order conflicts, including opposite-direction transfers.
Ledger insertion drives balance updates through database triggers; the service does
not separately adjust balances. Deferred checks preserve ledger/balance consistency
at commit. Database enforcement is layered through
[V3 balance/ledger integrity](../backend/banking-service/src/main/resources/db/migration/V3__balance_ledger_integrity.sql),
[V4 lifecycle integrity](../backend/banking-service/src/main/resources/db/migration/V4__transfer_lifecycle_integrity.sql)
and [V5 idempotency integrity](../backend/banking-service/src/main/resources/db/migration/V5__idempotency_integrity.sql).

**Tradeoff:** database locks and constraints add contention and migration complexity,
but enforce rules beyond one HTTP handler. Application-only validation or an
in-memory retry cache would leave direct SQL and process-restart gaps.

**Boundary and tests:** a reused key with different request details conflicts;
insufficient funds fail and roll back. This is scoped database idempotency, not a
guarantee of exactly-once delivery across external systems. See
[idempotency](../backend/banking-service/src/test/java/com/bankops/banking/IdempotencyIntegrationTests.java),
[lifecycle](../backend/banking-service/src/test/java/com/bankops/banking/TransferLifecycleIntegrationTests.java)
and [schema tests](../backend/banking-service/src/test/java/com/bankops/banking/BankingSchemaIntegrationTests.java).

## Read-only reconciliation and permissions

**Problem:** an independent checker needs consistent financial observations without
permission to repair or damage the records it checks.

**Choice:** [reconciliation](../airflow/reconciliation/__init__.py) reads a bounded
repeatable-read, read-only snapshot and rolls back even on success.
[Database grants](../database/permissions.sql) give the reconciliation role SELECT
on the required financial tables and schema history. [Task contracts](../airflow/reconciliation/tasks.py)
expose validated aggregate results rather than banking identifiers.

**Tradeoff:** separate credentials and schema checks cost setup effort. Reusing the
writer identity would be simpler but weaken the independent read boundary.
Bounded reads avoid unbounded work but cannot verify datasets beyond their limit.

**Boundary and tests:** unavailable permissions, incompatible schema or excessive
rows return INSUFFICIENT_DATA, not proof of corruption or health. New migrations
require reviewed grants. See [reconciliation tests](../airflow/tests/test_reconciliation.py),
[database permission tests](../backend/banking-service/src/test/java/com/bankops/banking/DatabasePermissionsIntegrationTests.java)
and the [Step 75 permission-fault scenario](verification/STEP75_INTEGRATION_REPORT.md).

## Apache Airflow scheduling

**Problem:** integrity checks need independent scheduled execution and visible
failure states, without being tied to a browser session.

**Choice:** the [daily DAG](../airflow/dags/bankops_reconciliation.py) orders
connectivity, reconciliation and validation tasks, with a final summary that still
fails when evidence is unavailable. The daily schedule disables catchup, permits
one active run and configures bounded retries.

**Tradeoff:** Airflow adds metadata, scheduler and deployment overhead compared
with cron. It provides explicit task states and scheduler history that the agent
can consume through its bounded viewer API.

**Boundary and tests:** a successful connectivity probe does not establish a valid
snapshot. The all-done summary must not mask upstream failure. See
[task/reconciliation tests](../airflow/tests/test_reconciliation.py) and the
[scheduled integration report](verification/STEP75_INTEGRATION_REPORT.md); that
fixture accelerates only a copied DAG, not the production schedule.

## Prometheus, Grafana and Jaeger

**Problem:** symptoms need aggregate metrics and request-level context without
exporting raw banking payloads into investigation reports.

**Choice:** [banking metrics](../backend/banking-service/src/main/java/com/bankops/banking/monitoring/TransferOutcomeMetrics.java)
feed Prometheus; [fixed aggregate queries](../agent/src/bankops_agent/evidence/prometheus.py)
supply detection, and [Grafana dashboards](../GRAFANA.md) expose trends.
[Jaeger collection](../agent/src/bankops_agent/evidence/jaeger.py) adds bounded,
sanitized trace summaries from OpenTelemetry instrumentation.

**Tradeoff:** multiple telemetry services increase operational cost but separate
trend detection from request investigation. Logs alone would not provide equivalent
rate/latency aggregates or trace hierarchy. No performance comparison is claimed.

**Boundary and tests:** scrape availability is not transaction readiness; idle
traffic can leave rate metrics missing. Correlation does not prove causality.
See [Prometheus integration tests](../agent/tests/test_prometheus_integration.py),
[Jaeger integration tests](../agent/tests/test_jaeger_integration.py),
[banking tracing tests](../backend/banking-service/src/test/java/com/bankops/banking/TracingIntegrationTests.java)
and [tracing failure tests](../backend/banking-service/src/test/java/com/bankops/banking/TracingFailureIntegrationTests.java).

## Python FastAPI evidence service

**Problem:** operators need one validated evidence contract while individual
upstream sources can fail, time out or return malformed data.

**Choice:** [application assembly](../agent/src/bankops_agent/app.py) owns configured
collectors, the graph and optional approval storage. FastAPI routes expose typed
reports while Pydantic validates bounded evidence; asynchronous collectors permit
independent source work without moving financial writes into the agent.

**Tradeoff:** a separate Python API introduces another deployment and cross-service
contracts. A browser that queried each telemetry backend directly would reduce one
service but distribute credentials and validation across clients.

**Boundary and tests:** health is process availability, not proof that every source
works. Unconfigured or unauthorized capabilities fail closed. See
[security tests](../agent/tests/test_security.py), [workflow tests](../agent/tests/test_workflow.py)
and the [API boundary](../agent/src/bankops_agent/security.py).

## Four-node LangGraph investigation

**Problem:** collect independent evidence while preserving deterministic detection
and an explicit point where optional model analysis begins.

**Choice:** [workflow.py](../agent/src/bankops_agent/workflow.py) starts detection
and evidence_collection in parallel, joins them at report_assembly, then runs rca.
Each invocation has fresh state; collectors stay in an application-owned closure.
Ambient LangSmith tracing is disabled for this path.

**Tradeoff:** a graph makes the join and analysis boundary inspectable, at the cost
of orchestration dependencies compared with a plain function. An autonomous tool
loop would add decisions and capabilities that this bounded workflow does not need.

**Boundary and tests:** no checkpointer, background watcher or remediation node is
configured. Partial sources remain partial; analysis failure preserves deterministic
evidence. See [workflow tests](../agent/tests/test_workflow.py) and
[workflow failure behavior](../agent/WORKFLOW.md).

## BM25 retrieval and citation validation

**Problem:** an investigation needs traceable operational guidance without treating
retrieval similarity or model text as verified causality.

**Choice:** [local retrieval](../agent/src/bankops_agent/rag/retrieval.py) uses BM25
and stable content-addressed source references. [RCA analysis](../agent/src/bankops_agent/rca/analysis.py)
checks output schemas, duplicate references, current evidence support and retrieved
source support locally. Retrieval can run with inference disabled.

**Tradeoff:** local lexical search avoids a hosted vector service and embedding
calls, but depends on vocabulary and a small reviewed synthetic corpus. Provider
schema enforcement alone would not establish that a citation actually supports a claim.

**Boundary and tests:** unsupported citations are rejected; supported hypotheses
still do not confirm a root cause. Cloud requests require a separate synthetic
profile and opt-in; successful live inference remains unverified. See
[retrieval tests](../agent/tests/test_rag.py), [mocked provider tests](../agent/tests/test_cloud_rag.py)
and [reconciliation grounding tests](../agent/tests/test_reconciliation_rag_boundary.py).

## Human-controlled approvals

**Problem:** an investigation or generated suggestion must not authorize its own action.

**Choice:** [approval API](../agent/src/bankops_agent/api/approvals.py) separates
proposer and reviewer credentials. [SQLite storage](../agent/src/bankops_agent/remediation/store.py)
records guarded terminal decisions and audit events. Approval performs no execution;
the separately gated [execution engine](../agent/src/bankops_agent/remediation/engine.py)
accepts only two read-only verification actions.

**Tradeoff:** explicit review and separate execution add operator steps compared
with automatic remediation. SQLite suits this bounded local workflow but does not
supply centralized identity or a signed, tamper-proof audit service.

**Boundary and tests:** possession of a reviewer credential does not prove physical
human presence. Filesystem owners remain trusted; per-person identity, SSO and MFA
are not implemented. Restart/scale proposal names are non-executable. See
[approval tests](../agent/tests/test_approvals.py),
[process integration](../agent/tests/test_approval_process_integration.py),
[execution integration](../agent/tests/test_remediation_process_integration.py)
and [approval limitations](../agent/APPROVALS.md).

## React operations dashboard

**Problem:** operators need to distinguish incidents, incomplete observations,
retrieved guidance and optional hypotheses without interpreting raw JSON.

**Choice:** the [incident page](../frontend/src/pages/Incidents.tsx) presents the
investigation and an expandable citation viewer. The
[report parser](../frontend/src/incidents.ts) validates incoming structures;
[the same-origin proxy](../frontend/proxy.ts) limits routes/methods and holds
service credentials on the server.

**Tradeoff:** React/TypeScript adds client parsing and UI state to maintain compared
with server-rendered reports. An interactive workspace makes evidence inspection
and explicit confirmation practical; it is not a substitute for server authorization.

**Boundary and tests:** invalid reports are rejected and citations are escaped text.
A responsive Chromium viewport is not physical-device verification; the Vite preview
proxy is not a production ingress. See [incident UI tests](../frontend/src/test/Incidents.test.tsx),
[citation tests](../frontend/src/test/RagCitations.test.tsx) and
[monitoring UI tests](../frontend/src/test/Monitoring.test.tsx).
