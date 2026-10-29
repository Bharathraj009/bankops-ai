# Live RCA verification

Run from `agent/` with the existing Python 3.12 environment:

```powershell
.\.venv\Scripts\python.exe -m bankops_agent.verify_rca
```

This default mode is fully local. It runs eleven synthetic scenarios through
the actual Prometheus, Jaeger and JSONL collectors, detection, LangGraph join,
report assembly, provider adapter and RCA validation. HTTP transports are
mocked; logs are generated in a disposable temporary directory. No running
banking, Prometheus, Jaeger, Grafana or agent service is required or contacted.
Ambient source URLs and log paths are not used.

## Provider and credentials

Supported providers are the provider-independent `json_http` gateway and the
`openai_compatible` Chat Completions adapter described in [RCA.md](RCA.md).
Inference defaults to `disabled`. Select the adapter matching the endpoint:
`json_http` expects direct analysis JSON; `openai_compatible` expects a chat
completion envelope. No vendor SDK or public API contract is introduced.

For real inference, configure the approved gateway in the process environment:

```powershell
$env:BANKOPS_AGENT_LLM_PROVIDER = 'json_http'
$env:BANKOPS_AGENT_LLM_URL = 'https://your-approved-gateway.example/rca'
$env:BANKOPS_AGENT_LLM_MODEL = 'rca'
# Inject BANKOPS_AGENT_LLM_API_KEY from your secret manager if the gateway requires it.
# Do not put keys in this document, command arguments, Git, or chat.
$env:BANKOPS_AGENT_LIVE_RCA_VERIFY = '1'
.\.venv\Scripts\python.exe -m bankops_agent.verify_rca --live
```

For Chat Completions, set `BANKOPS_AGENT_LLM_PROVIDER=openai_compatible`,
`BANKOPS_AGENT_LLM_URL` to the full approved chat-completions endpoint,
`BANKOPS_AGENT_LLM_MODEL` to a compatible available model, and inject the required
`BANKOPS_AGENT_LLM_API_KEY`. The same two opt-in controls apply. Normal automated
tests mock this path and never issue a paid API call.

Both the `--live` flag and `BANKOPS_AGENT_LIVE_RCA_VERIFY=1` are required, along
with valid enabled-provider configuration. Existing timeout/input/output/token
limits apply. Credentials are read only from environment variables; `.env`
files are not automatically loaded. The script never enables the application's
inference configuration or modifies its environment or config files.

After local fault checks, live mode makes **at most two inference calls**:
incident and contradictory-sample cases. Insufficient evidence executes the
complete graph but must make zero inference calls. Requests may incur provider
charges. There are no retries or remediation. Error/rate-limit/timeout injection
remains local rather than deliberately abusing a real provider. The gateway's
own retention and access controls remain its operator's responsibility.

## Synthetic scenarios and assertions

- Incident: 20 API requests/sec, 20% error ratio, p95 1.8 seconds, aggregate
  transfer failure observations, and a slow/failed database-call span.
- Insufficient: missing Prometheus observations, even with supporting trace/log
  samples; no model invocation and no healthy/confirmed conclusion.
- Contradictory sample: elevated aggregate errors with a fast, successful DB
  span. This sample does not disprove aggregate errors and does not support a
  DB-degradation hypothesis. The verifier checks that no DB evidence reference
  is manufactured. A separate unsupported-output case attempts that conclusion
  and must be rejected.
- Locally injected timeout, 429, 503, malformed JSON, missing body, unsupported
  hypothesis, high confidence and confirmed-root-cause claim: each must return
  its expected explicit undetermined reason while preserving the incident.

Each case checks the full graph result, one set of read-only evidence queries,
unchanged synthetic log contents, mandatory uncertainty, unconfirmed root cause,
and bounded confidence. Every hypothesis reference is independently checked
against a catalog reconstructed from the actual report and must support its
category. The input contains no account/transfer identifiers, monetary balances
or amounts, customer information, real logs, diagnostic IDs or raw messages.
Transfer rates are synthetic operational counts, not financial data.

## Results and exit codes

The script emits one allowlisted JSON summary, with no prompts, responses,
URLs, model names, keys, headers or exception text. Configuration reports only
the allowed provider name and booleans for URL/key presence. Argument errors
do not echo supplied values. Dependency logging is suppressed during CLI
execution and its previous configuration is restored afterward.

- `automated.transport="mocked"`: local scenario results, never live evidence.
- `live.status="not_requested"`: default; no real inference attempted.
- `live.status="blocked"`: required opt-in/configuration is absent or invalid.
- `live.transport="configured_gateway"`: actual configured provider used.
- `live.status="passed"` / `failed`: checks on real gateway responses.

Each case reports only its scenario, pass flag, incident/RCA statuses, bounded
reason, hypothesis count and inference-call count. Legitimate model abstention
is reported as `undetermined/no_supported_hypotheses` with zero hypotheses; it
can pass the contract checks but is not evidence of hypothesis generation.
Invalid or unavailable live responses cause a failed live verification, even
when safely rejected by production validation.

Exit **0** means all requested checks passed (or live checks were not requested).
Exit **2** means a failed check, live blocker, invalid arguments or safe execution
failure. Never interpret mocked success as real-provider verification. A passed
verification validates transport/grounding safeguards, not causal correctness
or calibrated confidence. Model behavior may vary on repeated calls.

## Recorded verification

The current process has no LLM configuration: provider defaults to `disabled`,
gateway URL is absent, bearer key is absent, and live opt-in is absent. Running
the opt-in entry point therefore reports `live.status="blocked"`, with no
real inference requests. To complete live verification, configure an approved
compatible gateway URL/model and any required environment-injected bearer key,
then supply both opt-in controls above.

October 15, 2026: **300 agent tests passed** with warnings treated as errors;
**202 banking tests passed**, zero failures/errors/skips, against disposable
PostgreSQL 17. All **11 synthetic verification scenarios passed**. Dependency
validation reported no broken requirements. The live command exited **2** with
the documented blockers; **zero real inference calls** were made. The disposable
test database was removed. V1–V5 hashes match the baseline, and banking source,
API contracts, Compose, monitoring and development services are unchanged.
