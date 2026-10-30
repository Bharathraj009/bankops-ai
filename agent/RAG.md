# Step 73B: document RAG and optional cloud analysis

The real four-node LangGraph remains detection, evidence_collection,
report_assembly and rca. Retrieval runs inside rca. Detection and source evidence
remain authoritative; generated output cannot execute tools or banking writes.

## Local retrieval

Set `BANKOPS_AGENT_RAG_ENABLED=true` to enable bounded JSON ingestion, overlapping
word chunks, an in-memory inverted index and BM25 retrieval. No embeddings, GPU,
downloaded model or local LLM is needed. Six bundled fictional incident and
troubleshooting documents produce stable content-hashed chunk IDs and
`corpus://synthetic/` references. Retrieval uses supported hypotheses derived
from validated rule/span evidence, rather than arbitrary user prompts.

Defaults: 80 words per chunk, 12 words overlap, four results (maximum six),
32 documents, 16,000 bytes per document, 1,024 chunks. `RAG_CHUNK_WORDS`,
`RAG_CHUNK_OVERLAP` and `RAG_TOP_K` configure bounded values. A trusted absolute
local `RAG_CORPUS_DIRECTORY` can supply JSON documents matching
`rag/models.py::Document`. Relative, UNC and reparse/symlink paths are rejected.
Only synthetic-classified documents are accepted. Ingestion redacts recognizable
identifiers and secrets; regex redaction cannot prove that arbitrary text is safe.
Custom documents remain local and do not gain export approval from metadata.

With inference disabled, investigations still return deterministic retrieval in
`rca.retrieval.sources`. A missing/invalid corpus fails closed. The HTTP API
exposes document citations; the dashboard renders reviewed synthetic sources in
an expandable citation viewer. Unreviewed local document titles/body remain hidden.

Step 75 adds reconciliation evidence-gap, integrity and task-failure mappings.
Only triggered, validated reconciliation rules enter this RAG-enabled grounding
path. INSUFFICIENT_DATA never implies financial corruption. Real operational
Airflow evidence remains local: external export policy is unchanged. For native
SafeEventLogger INFO context, explicitly enable LOG_INCLUDE_INFO and mount a
trusted JSONL source read-only; INFO is never projected as a warning hypothesis.
The disposable scheduler-to-dashboard harness is `local/run_step75.py`.

## Optional cloud profile

All settings use the `BANKOPS_AGENT_` prefix and must be supplied to the process;
Settings does not automatically load example files. Keep the default
`LLM_PROVIDER=disabled` and `LLM_EXTERNAL_OPT_IN=false` for offline work.
To prepare a synthetic demonstration, use:

```text
BANKOPS_AGENT_RAG_ENABLED=true
BANKOPS_AGENT_EVIDENCE_MODE=synthetic_demo
BANKOPS_AGENT_SYNTHETIC_SCENARIO=http_errors
BANKOPS_AGENT_LLM_PROVIDER=disabled
BANKOPS_AGENT_LLM_EXTERNAL_OPT_IN=false
```

Only after a separately authorized decision to incur provider costs, set
`LLM_PROVIDER=openai_cloud`, an explicit supported `LLM_MODEL` (for example
`gpt-5-mini`, subject to account availability), inject `LLM_API_KEY` through the
environment/secret manager, and set `LLM_EXTERNAL_OPT_IN=true`. Never place a
real key in Git, command arguments, examples or logs. The endpoint is fixed to
`https://api.openai.com/v1/chat/completions`; an alternative URL is rejected.
`LLM_CHAT_INCLUDE_STORE=true` means include the wire field **store=false**;
setting it false is rejected by the cloud adapter. No SDK is required.

The synthetic profile replaces observability collectors with server-owned
fictional fixtures, and rejects enabled Airflow access or remediation. Only
exact allowlisted observation enums/IDs and checksum-approved bundled document
chunks can leave the process. Timestamps, numeric operational measurements,
trace/customer identifiers and arbitrary text are excluded. Every cloud request
is checked even with a mocked transport. Legacy adapters also require the
outbound policy for real transports. No external inference happens on startup
or health checks; the authorized workflow POST is the inference path.

Responses must match the strict schema and cite both current supporting evidence
and retrieved chunks supporting the same hypothesis. Invented, duplicate,
missing or unsupported citations, free-form claims/commands and confirmed root
causes are rejected. This is bounded hypothesis selection, not proof of causality.
Human proposer/reviewer separation remains required; no model action executes.

The adapter uses a single bounded request without redirects, retries or proxy
inheritance. Failures preserve deterministic evidence and return a safe reason.
Default request timeout is five seconds and output cap 512 tokens; reasoning
models may need deliberate budget tuning and can return incomplete output,
which is rejected. No provider/account availability has been verified live.

Costs depend on input/output tokens and the selected model's current rates:
`input_tokens * input_rate + output_tokens * output_rate` (using matching rate
units). No free allowance is assumed; input bytes/output caps do not guarantee
a monetary budget. Check [model pricing](https://developers.openai.com/api/docs/models/gpt-5-mini)
before opting in. `store=false` is not a zero-retention guarantee; review
[provider data controls](https://developers.openai.com/api/docs/guides/your-data).
The request uses [Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)
and [structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs),
with independent local validation.

The bundled demo collector timestamps are fixed at app creation. Restart a demo
older than the evidence freshness window (default 60 seconds); stale evidence
correctly prevents inference. This limitation does not affect live collectors.

## Offline verification

From `agent`, run `.venv/Scripts/python.exe -m pytest tests/test_rag.py tests/test_cloud_rag.py -v`
and `.venv/Scripts/python.exe -m pytest -q -W error -p no:cacheprovider`.
The cloud integration tests inject `httpx2.MockTransport` and block the actual
`httpx2.AsyncHTTPTransport` so they cannot make provider network requests.
Passing mocked inference is not evidence of successful real inference.
