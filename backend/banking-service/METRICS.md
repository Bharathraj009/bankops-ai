Actuator exposes only `/actuator/health` and `/actuator/prometheus` over HTTP.
For the Docker Prometheus server and optional separate management listener, see
[the Prometheus setup guide](../../PROMETHEUS.md).
Health details remain hidden. Prometheus pulls metrics; transfers do not contact
a monitoring server or publish telemetry within financial transactions.

Spring Boot/Micrometer supply HTTP counts, cumulative latency and histogram buckets
as `http_server_requests_seconds_count`, `_sum`, and `_bucket`. HTTP labels are
restricted to bounded method, status, outcome and an allowlisted URI template;
other paths collapse to `OTHER`. Exception/error labels and arbitrary common tags
are removed from HTTP metrics. UUIDs, raw paths, keys and customer data are never
used as labels.

`bankops_transfer_outcomes_total` counts completed HTTP responses after services
and transaction commits. Its only labels are `operation` (`transfer`, `dev_funding`)
and `outcome` (`completed`, `replayed`, `invalid_request`, `account_not_found`,
`idempotency_conflict`, `rejected`, `server_error`, `other`). It describes HTTP
operation outcomes, not individual transfers or balances. Registry errors in this
best-effort observer are swallowed and cannot affect responses or money movement.

Example PromQL:

```promql
sum(rate(http_server_requests_seconds_count[5m]))
sum(rate(http_server_requests_seconds_count{status=~"4..|5.."}[5m])) / sum(rate(http_server_requests_seconds_count[5m]))
histogram_quantile(0.95, sum by (le) (rate(http_server_requests_seconds_bucket[5m])))
sum by (outcome) (rate(bankops_transfer_outcomes_total[5m]))
```

Integration tests exercise health/scraping, HTTP status and latency series,
transfer/retry/conflict/rejection counters, absence of sensitive values, and a
failing outcome registry while real transfers commit once and retries remain safe.
