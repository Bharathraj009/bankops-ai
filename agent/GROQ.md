# Groq RCA integration

The Groq profile uses the `openai_compatible` provider with:

- Endpoint: `https://api.groq.com/openai/v1/chat/completions`
- Model: `openai/gpt-oss-20b`

Groq documents strict schema support in its
[Structured Outputs guide](https://console.groq.com/docs/structured-outputs).
Its [API reference](https://console.groq.com/docs/api-reference) supports
`max_completion_tokens`, but marks `store` unsupported. The Groq profile omits
`store` via `BANKOPS_AGENT_LLM_CHAT_INCLUDE_STORE=false`. Other providers retain
the existing default `store=false`. Omission does not establish a provider-side
retention guarantee. No SDK, fallback request or schema downgrade is added.

## Disabled configuration

[.env.groq.example](.env.groq.example) contains the prepared profile without
credentials. It is not loaded automatically; inference remains **disabled**.
Equivalent preparation for the shell that will launch the agent:

```powershell
$env:BANKOPS_AGENT_LLM_PROVIDER = 'disabled'
$env:BANKOPS_AGENT_LLM_URL = 'https://api.groq.com/openai/v1/chat/completions'
$env:BANKOPS_AGENT_LLM_MODEL = 'openai/gpt-oss-20b'
$env:BANKOPS_AGENT_LLM_CHAT_INCLUDE_STORE = 'false'
$env:BANKOPS_AGENT_LLM_TIMEOUT_SECONDS = '30'
$env:BANKOPS_AGENT_LLM_MAX_INPUT_BYTES = '32768'
$env:BANKOPS_AGENT_LLM_MAX_OUTPUT_BYTES = '16384'
$env:BANKOPS_AGENT_LLM_MAX_OUTPUT_TOKENS = '2048'
$env:BANKOPS_AGENT_GROQ_LIVE_VERIFY = '0'
$env:BANKOPS_AGENT_LIVE_RCA_VERIFY = '0'
```

Inject the actual key as `BANKOPS_AGENT_LLM_API_KEY` from environment/secrets
management. If your secret manager provides `GROQ_API_KEY`, assign it to that
namespaced variable without printing it. No real credential appears in source,
examples or logs. Test tokens are explicitly synthetic; mocked checks require
no credential. Actual model access, speed and output quality remain unverified.
The 2048-token cap stays within existing limits; truncated completions fail safely.

## Exactly two prepared scenarios

From `agent/`, this default command makes no network calls:

```powershell
.\.venv\Scripts\python.exe -m bankops_agent.verify_groq
```

It executes actual collectors with mocked HTTP transports and a disposable
synthetic JSONL file, then detection, report assembly and RCA through LangGraph:

1. **Elevated transfer failure rate:** 0.3 failures/sec, 2.3 total transfer
   requests/sec; other metric rules remain below threshold. Expected rule and
   reference: `high_transfer_failure_rate` / `rule.high_transfer_failure_rate`;
   hypothesis `transfer_failure_degradation`.
2. **High banking API latency:** p95 1.8 seconds at 20 API requests/sec; other
   metric rules remain below threshold. Expected rule and reference:
   `elevated_p95_latency` / `rule.elevated_p95_latency`; hypothesis `latency_degradation`.

The verifier requires exactly the expected triggered rule and a compatible
hypothesis backed by the actual returned rule observation. It independently
checks every reference, confidence bounds, mandatory uncertainty, an unconfirmed
root cause and unchanged synthetic source contents. No account/transfer IDs,
balances, amounts, personal information, real logs, trace/correlation IDs or raw
messages are sent. Transfer rates are synthetic operational counts, not money.

## Live opt-in and request cap

**No live API calls were executed in Step 45.** For a later explicitly approved
verification only, after securely injecting the key and setting the exact profile:

```powershell
$env:BANKOPS_AGENT_LLM_PROVIDER = 'openai_compatible'
$env:BANKOPS_AGENT_GROQ_LIVE_VERIFY = '1'
.\.venv\Scripts\python.exe -m bankops_agent.verify_groq --live
```

Both the CLI flag and dedicated environment opt-in are required. The script
checks the exact endpoint, model and omitted-store profile before any request.
The generic `BANKOPS_AGENT_LIVE_RCA_VERIFY` flag does not enable this verifier.
Normal agent inference separately requires explicit enabled-provider configuration.

A shared, lock-protected budget allows **two total inference attempts per
invocation**, one per scenario. Failures consume their slot: no refunds, retries,
repair prompts or fallback calls. The HTTP transport explicitly uses `retries=0`,
no redirects and no environment proxies. Repeated manual invocations intentionally
start separate budgets; this is not an account-wide quota.

Output is allowlisted JSON: `mode` (`mocked` or `live`), status, scenario outcomes,
bounded reasons and attempt count. No prompts, responses, keys, headers or
exception text are printed. Exit 0 means both checks passed; exit 2 indicates
a blocker, failed check or safe execution error. Legitimate model abstention
remains undetermined but does not pass hypothesis-generation verification and
never triggers a retry.

Strict RCA schemas, evidence grounding, source limits, exact-ID correlation,
timeouts and API contracts remain intact. 429, unavailable and malformed outputs
remain explicit undetermined results without erasing the incident. No model
tools, remediation, financial writes or banking API/database access exist.
LangSmith tracing remains disabled. Banking source, V1–V5, Compose and monitoring
are unchanged.

## Verification results

October 15, 2026: **362 agent tests passed**, warnings treated as errors,
including **17 Groq-specific tests**. Both synthetic scenarios also passed the
standalone verifier in explicitly labeled mocked mode. Fault tests verify
timeouts, 429/unavailable responses, malformed/invented conclusions, opt-in
guards, credential redaction, exact scenario grounding, and the shared request
budget under failure/concurrency. Dependency validation passed.

The banking suite passed **202 tests**, with zero failures, errors or skips,
against disposable PostgreSQL 17, removed afterward. V1–V5 hashes match the
baseline. **Zero live Groq inference requests** were sent; credentials, account
access, real response quality and provider latency were not verified.
