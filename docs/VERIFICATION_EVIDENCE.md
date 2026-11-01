# Reconlith verification evidence

This is an index of existing authored public records, not a fresh test run.
Counts belong to their dated source and must not be added across overlapping suites.
Raw local reports, credentials and runtime logs are not reproduced here.

| Evidence | Scope and result | What it does not establish |
| --- | --- | --- |
| [Step 73, 2026-10-29](verification/STEP73_E2E_REPORT.md) | Local service checks plus isolated financial/security fixtures; distinguishes retained development images from disposable integration images. | A fixture pass does not update or validate every path in the retained stack. |
| [Step 73B, 2026-10-29](verification/STEP73B_RAG_REPORT.md) | Repairs and verification of retrieval/provider transport tests; provider calls mocked. | Successful live inference or provider availability. |
| [Step 74, 2026-10-29](verification/STEP74_INTEGRATION_REPORT.md) | Connected synthetic investigation slices and browser verification. | Full running-stack integration; the report explicitly records that gap. |
| [Step 75, 2026-10-29](verification/STEP75_INTEGRATION_REPORT.md) | Actual Airflow scheduled run through real APIs, LangGraph, BM25 and desktop/mobile-sized Chromium in a disposable synthetic fixture. | Financial corruption, physical mobile testing, automatic incident watching or production readiness. |
| [Hosted baseline 36a88e8, 2026-10-30](verification/HOSTED_36A88E8.md) | Four application CI jobs passed; seven image scans/SBOMs completed, five security gates blocked. | Security clearance or a current scan of later changes. |
| [Quality review, 2026-10-30](verification/QUALITY_AUDIT_2026-10-30.md) | Documentation, publication scope and lightweight contract checks. | A rerun of full application suites or integration. |

## Component and failure coverage

These are recorded results from [Step 73](verification/STEP73_E2E_REPORT.md),
2026-10-29. They precede Step 75 and are not additional tests to sum with it.

| Area | Recorded result and coverage | Source tests |
| --- | --- | --- |
| Banking integrity | 219 tests, zero failures/errors/skips; ledger consistency, rollback, concurrent retries and authorization. | [Transfer HTTP/concurrency](../backend/banking-service/src/test/java/com/bankops/banking/TransferApiIntegrationTests.java), [idempotency](../backend/banking-service/src/test/java/com/bankops/banking/IdempotencyIntegrationTests.java) |
| Agent | 487 regressions; disabled, mocked and adversarial LangGraph paths are separately recorded. | [Workflow](../agent/tests/test_workflow.py), [RCA](../agent/tests/test_rca.py) |
| Airflow/database | 59 regressions; read-only access and RBAC, with real DAG execution separately documented. | [Reconciliation](../airflow/tests/test_reconciliation.py), [provisioning](../database/tests/test_provision.py) |
| Frontend | 104 component tests and 32 standard Chromium tests; separate live security/browser projects are not included in those counts. | [Incident UI](../frontend/src/test/Incidents.test.tsx), [citation viewer](../frontend/src/test/RagCitations.test.tsx) |
| Failure injection | Isolated database outage/rollback, controlled banking incident and recovery passed in the report's disposable environment. | [Dated scenario descriptions](verification/STEP73_E2E_REPORT.md) |

[Step 73B](verification/STEP73B_RAG_REPORT.md) explains mocked provider transport
repairs; [retrieval tests](../agent/tests/test_rag.py),
[cloud-mock tests](../agent/tests/test_cloud_rag.py) and
[Step 75 grounding tests](../agent/tests/test_reconciliation_rag_boundary.py)
cover retrieval and local citation rejection. Passing tests do not establish
that a model identified a real cause.

## Actual Step 75 outcome

A temporary SELECT-permission restriction on schema-history metadata left database
connectivity working but prevented reconciliation from validating its source.
The collector reported insufficient_data and detection triggered
reconciliation_insufficient_data. Expected validator failures made the scheduled
DAG fail; observing that intended incident through the dashboard was the integration pass.

| Step 75 field | Actual historical synthetic-test outcome |
| --- | --- |
| RCA | Undetermined |
| Cloud inference | Disabled |
| Generated hypotheses | None |
| Retrieval | Verified: matched reviewed local runbook |
| Citations | Verified: source viewer expanded in desktop/mobile-sized Chromium |

RCA was **Undetermined**, reason **disabled**, with **no hypotheses**. Inference
was disabled. Matched local runbook retrieval supplied citations, not a confirmed
cause. Evidence remained **partial**, including six missing idle banking metrics.
No banking transactions were invented to fill those gaps. The fixture's financial
tables stayed empty and before/after snapshots matched.

The report records **544 agent tests passed, two opt-in browser tests skipped**,
**62 focused frontend tests**, and **seven focused Java tests**. The 108 focused
agent checks overlap the complete suite. These counts are historical, not results
of this documentation change.

## Browser, provider and local-stack boundaries

- Ordinary frontend tests and Step 74 browser slices use synthetic fixtures.
  The README screenshot is a static preview with no service requests.
- Step 75 used actual scheduler/API/browser connections with synthetic data and
  fixture infrastructure, without frontend API interception or fake Airflow responses.
- Provider tests use mocked transports; no successful live cloud inference is established.
- The [normal launcher](../local/README.md) runs without cloud inference. Full
  scheduled evidence and native log ingestion require extra configuration. Fixture
  TLS/token/log plumbing is not proof of a production pipeline or of identical
  configuration on the retained development stack.

## Hosted CI and unresolved security findings

The recorded [application run](https://github.com/Bharathraj009/bankops-ai/actions/runs/41060960966)
passed all four jobs for 36a88e8. Its [image run](https://github.com/Bharathraj009/bankops-ai/actions/runs/41060960956)
had five blocked gates: agent, airflow, airflow-test, frontend and database.
Banking and Jaeger passed that scan. The [authored artifact review](verification/HOSTED_36A88E8.md)
records 44 unique HIGH advisory/package/version findings across eight CVEs and
zero CRITICAL. These are dated findings, not a claim about today's advisory feed.

[Security policy](../SECURITY.md), [findings history](../security/README.md) and
[container inventory](../security/CONTAINER_FINDINGS.md) retain the disclosures.
The [image workflow](../.github/workflows/images.yml) retains strict HIGH/CRITICAL
gates including unfixed findings. Application test success does not override them.
See [testing instructions](TESTING.md) for commands and disposable-database requirements.
