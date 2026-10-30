# Optional LLM root cause analysis

The implemented analyzer combines a bounded evidence catalog with
[local retrieval and synthetic-data export controls](RAG.md). Real outbound
requests require RAG, synthetic demo evidence and explicit external opt-in.
The provider examples below describe adapter configuration; use the linked
RAG settings as well. Operational banking/observability evidence stays local.

For synthetic and opt-in live workflow checks, see
[LIVE_RCA_VERIFICATION.md](LIVE_RCA_VERIFICATION.md).

`POST /workflows/investigate` now adds an `rca` object to the existing
investigation report. `GET /incidents/investigate` is unchanged and never calls
an LLM. Detection, source statuses, exact-ID correlations and all original
report fields remain authoritative and unchanged by model output.

The graph joins detection and supporting evidence at report assembly, then
runs `rca`, then ends. An RCA/provider failure preserves the investigation
report and returns an explicit `undetermined` RCA, rather than failing evidence
collection. No remediation, tools, commands, financial writes or banking
API/database calls are available to the model.

## Configuration

All variables use the `BANKOPS_AGENT_` prefix. Defaults disable external inference.

| Suffix | Default | Meaning / bounds |
| --- | --- | --- |
| `LLM_PROVIDER` | `disabled` | `disabled`, `json_http`, `openai_compatible` or `openai_cloud`; see RAG.md for export policy |
| `LLM_URL` | unset | Full endpoint for `json_http`/`openai_compatible`; `openai_cloud` uses the fixed endpoint in RAG.md |
| `LLM_API_KEY` | unset | Required bearer key for `openai_compatible`/`openai_cloud`; optional for `json_http`; excluded from logs/evidence |
| `LLM_MODEL` | `rca` | Gateway model identifier, 1–100 restricted characters |
| `LLM_TIMEOUT_SECONDS` | 5 | Total analysis deadline, greater than 0 and at most 30 |
| `LLM_MAX_INPUT_BYTES` | 32768 | Full serialized inference request budget, 1024–65536 |
| `LLM_MAX_OUTPUT_BYTES` | 16384 | Decoded response byte cap, 256–32768 |
| `LLM_MAX_OUTPUT_TOKENS` | 512 | Requested gateway token cap, 128–2048 |
| `LLM_CHAT_INCLUDE_STORE` | true | Send `store=false` in Chat Completions; use false for Groq, which does not support that field |

Use HTTPS. Plain HTTP is allowed only for literal loopback/localhost gateways
outside production. URL userinfo, queries and fragments are rejected. No caller
can supply an endpoint, model, evidence, prompt, tool or workflow setting.
Keep credentials in environment/secrets management, outside Git.

## Provider-independent interface

`LLMProvider.analyze(evidence: dict, schema: dict) -> bytes` is asynchronous.
It returns raw UTF-8 JSON for local validation. New adapters can implement this
protocol without changing graph nodes or report schemas. The supplied
`JsonHTTPProvider` performs a single POST to the configured URL with:

```json
{
  "model": "rca",
  "instructions": "fixed server-owned analysis instructions",
  "evidence": {"incident_state": "incident", "evidence_status": "partial", "observations": []},
  "response_schema": {},
  "max_output_tokens": 512
}
```

The gateway must implement this request contract and return the analysis JSON
directly, with no vendor wrapper or Markdown fences. `response_schema` is the
actual generated strict JSON schema, not the empty illustrative value above.
This adapter is not a vendor-specific chat-completions client. A gateway may
route to a chosen provider; no provider SDK, model key or live provider is needed
for local tests. There are no automatic retries, redirects or environment-proxy
inheritance. HTTP 429 maps to `rate_limited`; other non-200 responses/network
failures map to `unavailable`. Timeouts map to `timeout`. Remote errors, bodies,
headers and credentials are never echoed or logged by the analyzer.

### OpenAI-compatible Chat Completions

See [GROQ.md](GROQ.md) for the disabled Groq profile and its two-scenario verifier.

Set `BANKOPS_AGENT_LLM_PROVIDER=openai_compatible` to use a Chat Completions
endpoint directly, without a JSON gateway or vendor SDK. The provider-independent
`analyze(evidence, schema) -> bytes` interface and downstream validation are
unchanged. Required process configuration:

```powershell
$env:BANKOPS_AGENT_LLM_PROVIDER = 'openai_compatible'
$env:BANKOPS_AGENT_LLM_URL = 'https://api.openai.com/v1/chat/completions'
$env:BANKOPS_AGENT_LLM_MODEL = 'your-chat-model'
# Inject BANKOPS_AGENT_LLM_API_KEY via your environment/secret manager.
# Never put a key in Git, chat, command arguments or logs.
```

Use the full approved endpoint URL, not a base URL: no suffix is appended.
The API key is required, cannot contain whitespace/control/non-ASCII characters,
and is sent only in the Authorization bearer header. Set a real model available
to your provider/account; the default `rca` identifier is a gateway placeholder,
not a selected hosted model. Defaults remain `disabled`; no startup, health,
GET investigation, or automated test command makes paid inference requests.

The adapter sends fixed system instructions, the sanitized evidence as a JSON
user message, `response_format.type=json_schema` with the exact RCA schema and
`strict=true`, `max_completion_tokens`, `n=1`, `stream=false`, and by default
`store=false` (omitted when explicitly configured).
There are no tools or arbitrary caller-supplied messages. This follows the
[official OpenAI Chat Completions reference](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)
and [Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs).

The endpoint/model must support this request subset, including strict schema
output, the schema's array bounds, and `max_completion_tokens`. Compatibility
with every vendor or fine-tuned model is not claimed. Unsupported parameters
or schema return a safe unavailable result; there is no automatic retry,
parameter downgrade, JSON-mode fallback or schema weakening. No API call was
made to select a model or verify account access.

Only one assistant choice at index zero, completed with `finish_reason=stop`,
with nonempty string content is accepted. Refusals, tool/function calls,
truncated/filtered completions, multi-choice results, malformed/duplicate JSON
envelope fields and unsupported content formats yield `invalid_output`.
Envelope metadata and provider diagnostics are discarded. Extracted content
still undergoes the independent strict RCA schema, evidence-reference,
confidence and hypothesis validation; a provider's schema guarantee is never
trusted alone.

The adapter checks the full serialized chat request against `LLM_MAX_INPUT_BYTES`
in addition to the analyzer's conservative preflight. `LLM_MAX_OUTPUT_BYTES`
bounds the entire decoded HTTP envelope, then the extracted content. Envelope
overhead therefore counts toward the output budget. Authentication failures,
unsupported requests and other non-200 responses map to `unavailable`; 429 maps
to `rate_limited`; transport/wall-clock timeouts map to `timeout`. Raw errors,
refusal text, keys and completion metadata are never returned or logged by the
adapter. TLS verification, no redirects, no retries and proxy isolation match
the existing gateway provider. `store=false` requests no completion storage;
the provider's separate logging/retention policy remains its responsibility.

Existing workflow/API response contracts do not change. The opt-in verification
CLI also supports this provider; its default remains local mocked checks. Do
not invoke live verification unless real, potentially paid inference is intended.

## Input and grounding

Inference requires a confirmed **incident rule observation**, not a confirmed
root cause. Healthy and insufficient-data investigations skip inference and
return `undetermined/insufficient_evidence`. Disabled inference returns
`undetermined/disabled` for incident reports.

The analyzer builds a second allowlisted projection from the sanitized report:
up to four triggered rule observations, ten slow/failed database-call span
observations, and ten WARN/ERROR log observations. Fields contain generated
references, fixed observation categories, timestamps and finite numeric values.
Raw messages, exceptions, span names/attributes, account/transfer identifiers,
trace IDs, correlation IDs, request paths and personal data are not sent.
The full investigation retains its existing safe exact-ID correlations locally.

References such as `rule.high_http_error_rate`, `span.0.2` and `log.0` refer only
to this request's returned evidence catalog. Span/log indexes refer to the
bounded original report. The input, including instructions/schema, is checked
against the byte budget before invoking a provider. Oversize input yields
`undetermined/input_limit`; no silent truncation changes an observation.

Logs and traces are untrusted data, never instructions. The prompt says so,
but the stronger boundary is structural: untrusted free text and diagnostic IDs
are excluded, output has no free-text fields or executable actions, and local
validation rejects unsupported references/categories. A provider cannot add
new observations, alter the investigation, request tools, or execute actions.

## RCA output contract

The `rca` object includes:

- `status`: `hypotheses` or `undetermined`;
- `root_cause_confirmed`: always `false`;
- `analyzed_at`: UTC analysis/fallback timestamp; investigation `completed_at`
  continues to mark completion of evidence/report assembly before analysis;
- `reason`: `supported_hypotheses`, `disabled`, `insufficient_evidence`,
  `no_supported_hypotheses`, `timeout`, `unavailable`, `rate_limited`,
  `invalid_output` or `input_limit`;
- `hypotheses`: at most three distinct category selections, each with 1–5
  distinct `supporting_evidence` references and `confidence` of `low` or `moderate`;
- `evidence`: the safe catalog against which references were validated;
- `uncertainty`: bounded categories, always including `causality_unconfirmed`
  and `bounded_sample`, plus `incomplete_evidence` when collection was partial;
- `recommended_investigation_steps`: bounded, read-only categories such as
  `compare_metric_windows`, `inspect_safe_trace_timings`,
  `check_dependency_health`, `review_sanitized_error_events` and
  `collect_additional_evidence`. These are recommendations, never executed.

Hypothesis categories are `http_error_degradation`, `latency_degradation`,
`transfer_failure_degradation`, `service_unavailability`, and
`database_call_degradation`. Each symptom category requires its corresponding
triggered rule; database degradation requires an actually returned slow/failed
`db.call` span. WARN/ERROR log observations alone cannot establish any category.
Every cited reference must exist and support the selected category. Missing,
incompatible, repeated or invented references reject the entire model response.

The model supplies only `hypotheses`, `uncertainty` and
`recommended_investigation_steps` in its response. Extra keys, duplicate JSON
keys, missing fields, invalid categories/types, oversized output and malformed
JSON all yield `undetermined/invalid_output`. Empty hypotheses yield
`undetermined/no_supported_hypotheses`. Undetermined results have no hypotheses,
no model text, mandatory uncertainty, and a recommendation to collect evidence.

## Limitations

This is deliberately constrained hypothesis selection, not unrestricted prose
diagnosis. Symptoms and slow database spans do not prove a causal dependency
failure. Valid references prove that observations exist, not that a hypothesis
is correct. Confidence labels are uncalibrated qualitative model judgments;
high confidence and confirmed diagnoses are unsupported. Missing sources,
bounded sampling and mismatched collection windows remain visible. No missing
evidence is filled in. A model may decline to select a hypothesis.

LangSmith workflow tracing remains disabled. Provider request/response text is
not persisted or logged by this agent. An enabled external gateway receives
the sanitized projection; its own retention, logging and access controls must
be configured by its operator. Cancellation propagates. Inference is the only
new external operation, and is optional; all banking/evidence operations remain
read-only. Existing collection and privacy limits still apply independently.

## Verification

Step 43, October 15, 2026: **345 agent tests passed**, with warnings treated as
errors, including **45 OpenAI-compatible adapter tests**. The banking suite
passed **202 tests**, zero failures/errors/skips, on disposable PostgreSQL 17;
the container was removed afterward. Dependency validation passed. All provider
calls were mocked; no live/paid inference or model-access check was performed.
V1–V5 hashes match the baseline; banking code, API contracts, Compose, monitoring
and development services are unchanged.

October 15, 2026: **277 agent tests passed**, with warnings treated as errors,
including mocked valid/invalid/missing/malicious provider responses, grounding,
input/output budgets, timeouts, cancellation, rate limits, configuration,
untrusted evidence projection, workflow transitions, and the unchanged GET
contract. No live LLM or external provider credentials were used.
Dependency validation reported no broken requirements.

The existing banking suite passed **202 tests**, with zero failures, errors or
skips, against disposable PostgreSQL 17. The test container was removed.
V1–V5 hashes match the prior baseline; banking code, Compose, monitoring and
development services remain unchanged.
