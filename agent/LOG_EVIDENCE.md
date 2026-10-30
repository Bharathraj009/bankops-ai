# Structured log evidence

`GET /evidence/logs` reads one operator-configured local UTF-8 JSONL file.
It performs no writes and does not contact banking APIs or databases. Collection
is disabled by default. No URL, path, filename, or other query parameters are
accepted by this endpoint (HTTP 400); other methods receive HTTP 405.

## Configuration

Set these environment variables before starting the agent:

| Variable (`BANKOPS_AGENT_` prefix) | Default | Bounds / meaning |
| --- | --- | --- |
| `LOG_SOURCE_DIRECTORY` | unset | Absolute trusted local directory; not returned in evidence |
| `LOG_SOURCE_FILENAME` | `banking.jsonl` | Simple filename only; no separators, drive, or alternate stream |
| `LOG_WINDOW_SECONDS` | 300 | 1–3600 seconds |
| `LOG_MAX_EVENTS` | 100 | 1–500 events |
| `LOG_MAX_BYTES` | 1048576 | 1024–4194304 bytes per collection |
| `LOG_INCLUDE_INFO` | false | Include bounded native INFO events as context |

For example, supply `BANKOPS_AGENT_LOG_SOURCE_DIRECTORY=C:\bankops-logs` and
place `banking.jsonl` in that directory. The agent does not create the directory
or file. Configure the banking process's console capture separately; use UTF-8
JSONL, not Windows PowerShell's default UTF-16 redirection. For Docker, mount a
dedicated log directory read-only, set the directory to its container path, and
grant the non-root agent user read permission. Do not mount secrets or the host
filesystem. Environment files are not loaded automatically.

## Evidence and privacy

The response contains source, fixed service name, collection timestamp, window
start/end, status, truncation flag, and newest-first events. Events contain only:

- `timestamp` from ECS `@timestamp`, with a timezone, within the current window;
- `level`, `WARN`/`ERROR`, plus `INFO` when explicitly enabled;
- `event_type`, exactly `http_request_completed` or `transfer_outcome`;
- `correlation_id`, only a UUID-shaped value, otherwise null;
- `trace_id`, only a nonzero lowercase 32-digit hex value, otherwise null.

The ECS service must be `banking-service` and logger must be
`com.bankops.banking.observability.SafeEventLogger`. Messages, exceptions,
stack traces, HTTP paths, operation/outcome payloads, attributes, account and
transfer identifiers, and every other input field are discarded. Correlation
and trace identifiers link evidence to other sources; they are diagnostic
identifiers, not authentication or proof of a financial event. Only consume
trusted banking logs: a reader cannot determine whether someone deliberately
encoded sensitive information into a syntactically valid diagnostic ID.

Native banking safe events use **INFO**, including unsuccessful HTTP outcomes.
The default collector excludes them; set `BANKOPS_AGENT_LOG_INCLUDE_INFO=true`
to include their bounded context. INFO events retain their severity and do not
become warning hypotheses or causal evidence. An empty response is expected when
the file has no qualifying events under the selected level/window settings.

## Failure behavior and limitations

HTTP 200 evidence statuses are `not_configured`, `missing` (absent file or no
qualifying events), `unavailable` (read denied or unsafe source), `partial`
(malformed records or truncation), and `ok` (qualifying evidence). These are
collection states, not healthy/incident decisions. Errors never disclose paths
or exception text. Malformed lines are skipped; valid evidence remains available.

The reader inspects only the bounded tail, discards a potentially cut first
line, and parses at most 10,000 lines, each at most 16 KiB. It sorts this bounded
sample by timestamp, then applies the result limit. Older unseen records may
exist. Appended incomplete JSON is skipped and may be read on the next request.
Rotation is not followed and no directory globbing or background tailer exists.
Symlinks, Windows reparse points, nonregular files and UNC sources are rejected;
file identity is checked when opened. The source directory and ancestors must
be controlled by a trusted operator, not writable by untrusted users. Only
local regular files are supported: this does not provide a deadline for a
stalled disk or a network filesystem mounted behind a local path. File I/O runs
off the request event loop. Retention and access control remain deployment tasks.

Tests use temporary JSONL files and FastAPI HTTP requests, covering privacy,
correlation, ordering, bounds, malformed input, missing/denied sources, source
restrictions and read-only behavior. No running banking service is required.

## Verification

October 15, 2026: Python 3.12 suite **194 passed**, with warnings treated as
errors; dependency check reported no broken requirements. The existing banking
suite also passed **202 tests**, with zero failures, errors, or skips, against a
disposable PostgreSQL 17 container. The Maven wrapper failed before launching;
the cached Maven 3.10 installation with JDK 25 ran the suite successfully.
V1–V5 SHA-256 hashes match the prior baseline. Development services were left
running and unchanged; the disposable test container was removed.
