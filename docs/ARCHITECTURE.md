# Architecture and evidence boundaries

The operations dashboard calls a same-origin proxy. That proxy restricts routes,
methods and origins and supplies the server-held agent credential only to approved
agent routes. Financial operations remain in the banking API and PostgreSQL.
The agent has no financial database credentials or financial network membership.

## Real investigation graph

```mermaid
flowchart TD
  Start[Explicit workflow POST] --> D[detection]
  Start --> E[evidence_collection]
  D --> A[report_assembly: join]
  E --> A
  A --> R[rca: local retrieval and optional bounded analysis]
  R --> End[Evidence report with source references]
```

Detection uses validated metrics and optional bounded Airflow summaries. Supporting
evidence is collected from Jaeger and trusted local JSONL. Only safe identifiers,
timestamps, enums and aggregate fields enter reports; arbitrary upstream text is
not trusted as instructions. INFO log context is an explicit opt-in and never
becomes warning/causal evidence.

## Scheduled reconciliation to UI

```mermaid
sequenceDiagram
  participant Scheduler as Airflow scheduler
  participant DAG as Reconciliation DAG
  participant DB as PostgreSQL
  participant Operator as Human operator
  participant Agent as FastAPI / LangGraph
  participant RAG as Local BM25 index
  participant UI as React
  Scheduler->>DAG: Actual scheduled run
  DAG->>DB: Read-only connectivity and snapshot checks
  DAG-->>Scheduler: Bounded task states and XCom aggregate
  Operator->>UI: Explicitly confirm investigation
  UI->>Agent: Authorized workflow POST
  Agent->>Scheduler: Viewer-only GETs over verified TLS
  Scheduler-->>Agent: Validated task/summary evidence
  Agent->>RAG: Query supported incident kinds
  RAG-->>Agent: Reviewed chunks and stable source IDs
  Agent-->>UI: Deterministic report and local source references
```

The scheduled integration fixture temporarily restricted the reader's
schema-history
SELECT permission. Connectivity succeeded; reconciliation returned unavailable
evidence; validators failed intentionally. No banking records were changed.
The scheduled run, not a fabricated API response, reached Chromium. Initiation
of investigation remained manual and pull-based. See the [dated integration report](verification/STEP75_INTEGRATION_REPORT.md).

## Optional model path

Cloud inference is disabled by default. The supported adapter was exercised with
mocked transports; real inference is not claimed. External requests require a
separate synthetic-demo profile, explicit opt-in and canonical reviewed context.
Operational Airflow/banking evidence is blocked from export. Invalid, missing or
unsupported citations are rejected locally, independently of provider schemas.
Model output cannot propose arbitrary commands or directly write banking data.

Human approval uses distinct proposer/reviewer roles and explicit confirmation.
An approved record does not establish incident resolution. Execution and verification
have separate audit boundaries; the default runtime has remediation disabled.
