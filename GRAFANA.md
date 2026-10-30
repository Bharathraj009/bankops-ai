# BankOps AI Grafana dashboard

> For the complete current platform, use the [local runbook](local/README.md).
> The setup below describes the older root Compose/host-run arrangement, with
> different ports and manual database provisioning. Its dated observations are
> historical, not performance benchmarks or a statement that services run now.
> Root Compose requires `BANKOPS_POSTGRES_ADMIN_PASSWORD` and
> `BANKOPS_GRAFANA_ADMIN_PASSWORD`; `.env.example` alone does not provision the
> current migration/runtime identities. See [database setup](database/README.md).

Configure `.env` (ignored by Git) with a unique strong
`BANKOPS_GRAFANA_ADMIN_PASSWORD` and optionally `BANKOPS_GRAFANA_ADMIN_USER`
(default `admin`). `.env.example` contains placeholders only. Never commit real
credentials or print `docker compose config` with resolved secrets.

Start Spring Boot using the `dev,monitoring` profiles as described in
[PROMETHEUS.md](PROMETHEUS.md), then from the repository root:

```powershell
docker compose up -d prometheus grafana
```

Open <http://localhost:3000/d/bankops-ai> and log in with your local `.env`
credentials. Grafana's UI binds only to `127.0.0.1:3000`; anonymous access and
user signup are disabled. The default provisioned Prometheus data source uses
`http://prometheus:9090` on the Compose network, not browser localhost.

The dashboard refreshes every 15 seconds and includes:

- API request rate (requests/second).
- API error rate (fraction of HTTP 4xx and 5xx responses).
- API latency p95 (seconds).
- Successful transfer rate (new `completed` responses/second).
- Failed transfer request rate (unsuccessful HTTP responses/second).
- Application availability (`up`: 1 for UP, 0 for DOWN).

All rate queries use five-minute windows and filter `job="banking-service"`.
API panels filter URI templates starting `/api/v1/`; management traffic is
excluded. Transfer panels filter `operation="transfer"`, excluding development
funding and `replayed` retries. Failures describe HTTP outcomes rather than
persisted `FAILED` transfer records. Success and failure panels use zero fallback
only when a real transfer counter exists. Missing scrape targets remain No data;
latency is unavailable without observations. Allow at least two scrapes after
generating requests. A validation-rejected transfer POST can verify counters
without moving money. Existing metrics contain no financial identifiers.

Dashboard JSON and provisioning files are version controlled under
`monitoring/grafana/`. Provisioned resources are read-only in Grafana; edit their
source files to change them. Dashboard changes reload automatically; restart
Grafana after changing data-source provisioning.

Grafana state persists in the `bankops_grafana_data` named volume. Initial admin
credentials initialize a new volume; editing `.env` does not reset an existing
admin password. Use Grafana's authenticated account settings to change it.
Stop monitoring with `docker compose stop grafana prometheus`. Never use
`docker compose down -v`, which also removes PostgreSQL data.

Grafana health is at <http://localhost:3000/api/health>. For missing panels, check
the Prometheus target, Grafana data-source connection, and real traffic during
the selected time window. Exact PromQL expressions live in
`monitoring/grafana/dashboards/bankops-ai.json`.

Provisioning follows [Grafana's provisioning documentation](https://grafana.com/docs/grafana/latest/administration/provisioning/).

## Verification on October 14, 2026

Grafana 13.2.4 is healthy. The default data-source health check returned `OK`,
and Grafana reported the BankOps AI dashboard as provisioned with six panels.
Queries through Grafana's `/api/ds/query` returned:

| Panel | Observed value |
| --- | --- |
| API request rate | 0.051993 requests/second |
| API error rate | 53.9343% |
| API latency p95 | 0.127694 seconds |
| Successful transfer rate | 0/second |
| Failed transfer request rate | 0.028073/second |
| Application availability | 1 (UP) |

Verification generated account reads and deliberately invalid transfer requests;
no funds moved. The success panel's zero derives from real observed transfer
counters, not synthetic successful transfers. These values are window-dependent.
All six chart range queries also returned finite samples. Raw instant and range
responses are saved under `backend/banking-service/target/step29-grafana*-verification.json`.

The unauthenticated dashboard API returned HTTP 401. Container inspection confirmed
the localhost-only port binding, read-only provisioning mounts, and writable named
data volume. `.env` is ignored by Git. Existing PostgreSQL/Prometheus configuration,
banking Java code, and V1–V5 migration hashes remain unchanged.

The full isolated PostgreSQL suite passed: **187 tests, zero failures, errors or
skips**. Output is in `backend/banking-service/target/step29-tests.log`; the
disposable database was removed. Grafana, Prometheus and the previously started
Spring Boot monitoring process remain running.
