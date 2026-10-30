# Development Prometheus

> For the complete current platform, use the [local runbook](local/README.md).
> The setup below describes the older root Compose/host-run arrangement, with
> different ports and manual database provisioning. Its dated observations are
> historical, not performance benchmarks or a statement that services run now.
> Root Compose requires `BANKOPS_POSTGRES_ADMIN_PASSWORD` and
> `BANKOPS_GRAFANA_ADMIN_PASSWORD`; `.env.example` alone does not provision the
> current migration/runtime identities. See [database setup](database/README.md).

Prometheus scrapes the host-run banking service every 15 seconds at
`host.docker.internal:8081/actuator/prometheus`. Compose adds the host gateway
mapping for Docker compatibility. The optional `monitoring` Spring profile uses
a separate management listener on port 8081 and binds business APIs to loopback
on port 8080. Only health and Prometheus are exposed by Actuator; health details
remain hidden. Restrict inbound port 8081 to your local Docker network with your
host firewall; metrics are unauthenticated and intended for local development.
Do not enable this development setup on an Internet-facing host.

From the repository root, configure `.env` from `.env.example`, then run:

```powershell
docker compose up -d postgres prometheus
docker compose run --rm --no-deps --entrypoint promtool prometheus check config /etc/prometheus/prometheus.yml
```

Spring Boot does not automatically load Compose's `.env`. Set `BANKOPS_DB_USER`
and `BANKOPS_DB_PASSWORD` in the application shell to the same database credentials,
then start the application:

```powershell
cd backend/banking-service
$env:SPRING_PROFILES_ACTIVE = 'dev,monitoring'
.\mvnw.cmd spring-boot:run
```

Reserve bootstrap remains opt-in. Monitoring requires no account funding or
database changes. Existing profiles and API contracts remain unchanged when the
`monitoring` profile is absent.

Open <http://localhost:9090/targets> and confirm `banking-service` is **UP**.
Prometheus itself is healthy at <http://localhost:9090/-/healthy>.
The banking health endpoint is <http://localhost:8081/actuator/health>.
Use the Prometheus query UI or API:

```powershell
Invoke-RestMethod 'http://localhost:9090/api/v1/query?query=up%7Bjob%3D%22banking-service%22%7D'
Invoke-RestMethod 'http://localhost:9090/api/v1/query?query=http_server_requests_seconds_count'
Invoke-RestMethod 'http://localhost:9090/api/v1/query?query=bankops_transfer_outcomes_total'
```

HTTP series appear after requests complete. Transfer outcome series appear after
a transfer POST response, including a validation rejection or matching retry;
no money movement is needed to verify monitoring. See
[the application metrics guide](backend/banking-service/METRICS.md) for latency,
error-rate queries and bounded labels. If the target is DOWN, confirm the app is
running with `monitoring`, port 8081 is reachable from Docker, and inspect
`docker compose logs prometheus` and the target's last scrape error.

Prometheus data persists in the `bankops_prometheus_data` named volume. Stop only
monitoring with `docker compose stop prometheus`; restart it with
`docker compose up -d --no-deps prometheus`. Do not use `down -v`, which would also
remove PostgreSQL data. Changes to the scrape configuration require restarting
Prometheus (`docker compose restart prometheus`). No administration or lifecycle
HTTP APIs are enabled on Prometheus.

## Verified on October 14, 2026

- `promtool check config`: success.
- Prometheus container: healthy; configuration mount read-only; data mount is a
  named Docker volume.
- Target: `http://host.docker.internal:8081/actuator/prometheus`, health `up`,
  no scrape error; `up{job="banking-service"}` returned `1`.
- Banking health returned HTTP 200 with status `UP`. Management-port account
  API and `/actuator/env` returned HTTP 404.
- Empty transfer request returned HTTP 400 without money movement. Prometheus
  subsequently returned HTTP request count `1`, latency sum `0.1982913` seconds,
  69 histogram bucket series, and transfer outcome
  `{operation="transfer",outcome="invalid_request"}` with value `1`.
- Existing isolated PostgreSQL suite: **187 tests, zero failures, errors or
  skips**. The disposable test container was removed after testing.
- PostgreSQL Compose configuration and V1–V5 migration hashes are unchanged.

Raw query results are in `backend/banking-service/target/step28-prometheus-verification.json`;
test output is in `backend/banking-service/target/step28-tests.log`. Verification
left Prometheus and the monitoring-profile Spring Boot app running. The app's
PID is recorded in `backend/banking-service/target/step28-app.pid`; stop this
verification process, when desired, with:

```powershell
Stop-Process -Id (Get-Content backend/banking-service/target/step28-app.pid)
docker compose stop prometheus
```
