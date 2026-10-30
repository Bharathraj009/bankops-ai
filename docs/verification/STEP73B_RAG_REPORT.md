# Step 73B verification report

Verification date: 2026-10-29. All provider inference in this verification was
mocked. No real inference, paid API request, banking data export, push or
deployment was performed. Existing unrelated workspace changes were preserved.

## Reproduced failures and repairs

The requested targeted command reproduced **42 passed, 6 failed**. The test
rewrite imported `httpx`, whereas the production adapter imports `httpx2`.
These are separate transport implementations. Consequently its MockTransport
and network-blocking monkeypatch targeted the wrong library. Passing that
transport into the httpx2 client caused a local transport compatibility failure,
which the analyzer safely converted to `unavailable`.

| Failing case | Observed effect of the same import regression |
| --- | --- |
| Graph/http_errors | Expected hypotheses, got undetermined |
| Graph/latency | Expected hypotheses, got undetermined |
| Graph/service_down | Expected hypotheses, got undetermined |
| Provider HTTP 429 | Expected rate_limited, got unavailable before response processing |
| Invalid cloud citation | Expected invalid_output, got unavailable before citation validation |
| FastAPI workflow/approval integration | Expected hypotheses, got undetermined |

Changed the test import to `httpx2 as httpx`, matching production. The network
tripwire now also targets the production transport implementation. Added
structural assertions that exported observations have exactly id, source,
observation and supports. Preserved credential, source/citation, opt-in and
human-approval assertions. No production security check was relaxed.

The earlier broad substring `threshold` check was not the cause of these six
reproduced failures: the on-disk rewrite had already narrowed it to the JSON
field name. `threshold_reached` remains a valid observation enum, and approved
synthetic documentation may contain the ordinary word threshold.

The first full suite then exposed one older test incompatibility:
`test_groq.py::test_transport_explicitly_disables_retries_and_environment_proxy`
sent an empty payload. The new fail-closed guard correctly rejected it before
transport construction. Updated its fixture to approved synthetic context and
explicit opt-in; retained exact retries=0/trust_env=false verification and mocked
transport construction. Production guards were unchanged.

## Final verification results

- Requested targeted command: **48 passed in 5.19 seconds** (initial reproduction:
  42 passed, 6 failed in 5.47 seconds).
- Full agent command: `.venv/Scripts/python.exe -m pytest -q -W error -p no:cacheprovider`:
  **535 passed in 133.47 seconds**, no failures or skips.
- Frontend `npm run typecheck`: passed. Incident dashboard regression:
  `npm test -- src/test/Incidents.test.tsx`: **18 passed**, one test file.
  An earlier mistyped test filter selected no files; the corrected command above
  ran successfully. Vite emitted an existing future config-loader warning.
- Offline wheel build with `--no-deps --no-build-isolation --no-index`: passed;
  inspected archive contains all five corpus JSON files. Build artifacts remain
  under ignored `local/results/step73b/wheels`.
- Python compilation and Git whitespace checks: passed. Default-settings probe:
  provider disabled, external opt-in false, provider factory returns None.

Step 73B local implementation and required verification are complete. Real cloud
inference remains intentionally unexecuted and requires separate operator setup.

## Verified implementation

- Real four-node LangGraph execution is verified with parallel detection/evidence,
  report assembly and RCA. No additional graph/action node was introduced.
- Real local BM25 retrieval ingests, validates, chunks and indexes documents;
  relevance, overlapping chunks, stable source IDs and source references are tested.
  Five bundled reviewed synthetic documents are included in the built wheel.
- Cloud Chat Completions adapter and strict response parsing execute through
  httpx2.MockTransport. Real cloud connectivity/account access/model execution
  remain unverified. The default provider is disabled, external opt-in is false.
- Every RAG hypothesis requires supporting current evidence and valid retrieved
  citations for the same supported hypothesis kind. Invented/duplicate/missing
  citations, unsupported claims and confirmed root causes fail validation.
- Local deterministic investigation/retrieval survives disabled inference and
  provider failures. Human approval, role separation and disabled remediation
  remain enforced. Cloud output cannot write banking records.

## Security verification scope

Targeted tests cover synthetic provenance, checksum-approved sources, tampered
payload rejection, opt-in, operational export refusal, credential masking/log
absence, authentication, forbidden caller evidence and approval safeguards.
The actual provider network transport is blocked in cloud tests. Only exact
reviewed source content and projected fictional observation enums can export;
custom synthetic-labelled documents do not gain export permission.

Compile checks, wheel package-data inspection and Git whitespace checks pass.
HIGH/CRITICAL image gate remains strict with exit-code 1 and no ignore file;
no security workflow was changed. Existing image vulnerabilities were not
remediated or rescanned in this test-repair step. No migration, database record
or Docker volume was modified.

## Files changed during this continuation

- `agent/tests/test_cloud_rag.py`: correct transport module, structural assertions,
  remove unused imports.
- `agent/tests/test_groq.py`: authorized synthetic transport-policy fixture.
- `agent/.env.example`: explicit RAG/evidence mode/external opt-in defaults.
- `agent/RCA.md`: current outbound policy and RAG documentation link.
- `agent/RAG.md`: configuration, privacy, costs, source grounding and limitations.
- `STEP73B_RAG_REPORT.md`: this report.

Pre-existing Step 73B implementation changes in config/app/workflow/investigation,
RCA/provider, rag package/corpus, package-data and frontend reason labels were
reviewed and retained. Unrelated prior changes were not reset or discarded.

## Remaining operational limitations

See [agent/RAG.md](../../agent/RAG.md) for configuration and provider documentation.
Actual inference requires an operator-selected available model, externally
injected credentials, deliberate cost acceptance and explicit synthetic-only
opt-in. None was enabled here. store=false does not establish zero retention.
Lexical matching and rule-grounded hypotheses are not causal diagnosis. Custom
corpora require separate review/code approval before any export. The dashboard
does not yet display retrieved document details. Synthetic fixture timestamps
expire after the configured evidence freshness window; restart a demo to refresh
them. Operational collector freshness and existing security gates remain intact.
