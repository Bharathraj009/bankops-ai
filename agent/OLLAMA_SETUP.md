# Local Ollama preparation (Step 44)

## Observed system and readiness

Read-only inspection on October 15, 2026 found Windows 11 Home, an Intel
Core i7-1355U (10 cores / 12 logical processors), **15.69 GiB usable RAM** and
approximately **2.06 GiB available RAM** at inspection time. Graphics inventory
lists Intel Iris Xe and a virtual display adapter; no discrete GPU was identified.
Plan for CPU execution unless the installed Ollama build later demonstrates
usable acceleration. Actual speed has not been benchmarked.

Ollama was not found in PATH, its standard per-user/Program Files locations,
or running processes. The standard local model manifest directory was absent.
GET probes of these local endpoints were unavailable:

- `http://127.0.0.1:11434/api/version`
- `http://127.0.0.1:11434/api/tags`
- `http://127.0.0.1:11434/v1/models`

This establishes that the default local service is unavailable; it does not
exclude an installation at a custom path or a remote server. No installed model
could be listed. No Ollama installation, model download, service start, model
load, chat request or live inference was performed.

## Recommended model

Use **`qwen2.5:3b`**, the 3.09B Q4_K_M model with a roughly **1.9 GB download**.
Its model documentation emphasizes instruction following and structured JSON
output: [official model entry](https://ollama.com/library/qwen2.5:3b).
This is a modest first candidate for the agent's constrained hypothesis-selection
schema on this 16 GB laptop, rather than a claim of verified RCA quality.

The current ~2 GiB free RAM is insufficient headroom: weights are only part of
runtime memory, and the OS, context cache and existing services need room too.
As a conservative planning estimate, free approximately **5–6 GiB** before a
first attempt. This is not a measured model requirement. Keep banking and
monitoring services intact; use ordinary nonessential application cleanup or
more memory rather than stopping them. Large context windows are unnecessary
for the bounded RCA input. CPU cold starts may exceed the current 30-second
maximum request timeout; success and latency remain unverified.

## Compatibility blocker before live use

Ollama documents `/v1/chat/completions`, `/v1/models`, JSON response formats
and local placeholder bearer keys in its
[OpenAI compatibility guide](https://docs.ollama.com/api/openai-compatibility).
The intended agent URL is the full endpoint
`http://127.0.0.1:11434/v1/chat/completions`.

The existing adapter sends **`max_completion_tokens`**. Ollama's current guide
lists **`max_tokens`**, and its
[official request mapping](https://github.com/ollama/ollama/blob/main/openai/openai.go)
maps `max_tokens` to `num_predict`, with no `max_completion_tokens` field found
in the reviewed source. Therefore the adapter's intended 512-token generation
limit cannot currently be assumed effective with Ollama. The HTTP timeout and
response-byte caps still exist, but do not replace a model-side token cap.

Before enabling live use, a follow-up implementation should provide an explicit
token-parameter compatibility setting (preserving the existing default), or a
tested equivalent gateway mapping. Do not silently fall back or weaken the RCA
schema. Ollama's mapping accepts the supplied JSON schema; full schema behavior,
completion envelope and other request flags still need verification against an
actual installed version. No endpoint compatibility claim is based on a live
completion in this preparation step. Application/provider code was not changed.

## Required commands, for a later approved setup

1. Install Ollama using the [official Windows instructions](https://docs.ollama.com/windows).
   Installation was not performed here.
2. If its tray application is not already serving, start it in a separate terminal:

   ```powershell
   $env:OLLAMA_HOST = '127.0.0.1:11434'
   ollama serve
   ```

3. Verify the server and list models without inference:

   ```powershell
   ollama --version
   ollama list
   Invoke-RestMethod http://127.0.0.1:11434/api/version
   Invoke-RestMethod http://127.0.0.1:11434/v1/models
   ```

4. **Only after explicit model-download confirmation**, run:

   ```powershell
   ollama pull qwen2.5:3b
   ```

   `pull` downloads weights; it does not verify inference. Do not use `ollama run`
   or a chat-completions POST during preparation.

## Prepared environment configuration

[.env.ollama.example](.env.ollama.example) contains the prepared environment
values. It is not loaded automatically and does not alter a running agent.
Equivalent PowerShell settings for the shell that will launch the agent are:

```powershell
$env:BANKOPS_AGENT_ENVIRONMENT = 'dev'
$env:BANKOPS_AGENT_LLM_PROVIDER = 'disabled'
$env:BANKOPS_AGENT_LLM_URL = 'http://127.0.0.1:11434/v1/chat/completions'
$env:BANKOPS_AGENT_LLM_MODEL = 'qwen2.5:3b'
$env:BANKOPS_AGENT_LLM_API_KEY = 'ollama' # Non-secret placeholder, ignored locally.
$env:BANKOPS_AGENT_LLM_TIMEOUT_SECONDS = '30'
$env:BANKOPS_AGENT_LLM_MAX_INPUT_BYTES = '32768'
$env:BANKOPS_AGENT_LLM_MAX_OUTPUT_BYTES = '16384'
$env:BANKOPS_AGENT_LLM_MAX_OUTPUT_TOKENS = '512'
$env:BANKOPS_AGENT_LIVE_RCA_VERIFY = '0'
```

Leave `LLM_PROVIDER=disabled` and live verification opt-in off until installation,
RAM headroom, download approval and the token-parameter compatibility gap are
resolved. The application's existing default remains disabled. No live workflow
command is executed or needed for this step. All banking, migrations, monitoring
and existing API contracts are untouched.
