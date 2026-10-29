# BankOps AI

Enterprise Banking & AI Reliability Platform: Spring banking, a FastAPI
reliability agent, React, PostgreSQL, Airflow, Prometheus, Grafana and Jaeger.

## Quick start

Requires Python 3.12+, local Docker Desktop/Engine and Docker Compose 2.24.4+.
From the repository root:

```powershell
python local/platform.py up
```

The launcher generates private credentials only if absent, builds only missing
local images, allocates explicit subnets for new networks and waits for all nine
runtime containers. Existing networks and volumes are preserved. Cold Airflow
startup can take several minutes. No paid cloud service or inference key is needed.

If upgrading from Steps 67–68, adopt the frontend shutdown fix explicitly:

```powershell
python local/platform.py build frontend
python local/platform.py up
```

Source changes require an explicit `build`; ordinary startup never unnecessarily
rebuilds an available image. The root `compose.yaml` is the earlier infrastructure
stack; the unified platform uses `local/compose.yaml` through this launcher.

## Operate

```powershell
python local/platform.py health
python local/platform.py logs banking
python local/platform.py stop
python local/platform.py up
python local/platform.py restart frontend
python local/platform.py verify
python local/platform.py test
```

`stop` keeps containers, networks and every volume. `restart` without a service
performs a health-gated full stop/start. `verify` checks real service routes and
SELECT-only reconciliation using Python stdlib + the running containers. `test`
requires the project's developer Python/Playwright dependencies; `test --recovery`
runs faults only against a fresh disposable project, never the ordinary platform.

## Service access

| Service | Local URL |
| --- | --- |
| React workspace | http://127.0.0.1:15173 |
| Airflow | http://127.0.0.1:18087 |
| Prometheus | http://127.0.0.1:19097 |
| Grafana | http://127.0.0.1:13007 |
| Jaeger | http://127.0.0.1:16687 |

Banking, the agent and both databases have no published host ports. Approved
frontend proxies preserve operator/reviewer authentication. Open ignored
`local/.env.local` in your local editor for the operator credential and local UI
passwords (`localadmin`/`agentviewer` for Airflow; `admin` for Grafana). Never paste
credentials or resolved Compose environments into logs or Git. Customer APIs,
inference and remediation are disabled by default; no automatic funding is enabled.

## Troubleshooting and limits

Use `health`, then `logs <service>`; inspect `prepare`, `migrate`, and `grant` if
banking cannot start. Do not reset passwords, delete volumes or bypass failed
migrations. A metrics scrape does not establish transaction readiness, and low
traffic can correctly show insufficient monitoring evidence.

For a NEW project whose host/VPN routing needs another private range:

```powershell
python local/platform.py --network-pool 10.70.0.0/16 up
```

The default is 10.69.0.0/16, divided into unused /24s after Docker network
inspection. Saved plans cannot silently change existing networks. No daemon-wide
settings, network pruning or destructive cleanup are performed. The host's default
automatic pool remains exhausted from retained projects; explicit local IPAM
avoids using it. Host/VPN routes must still suit the selected pool.

This is a local demo environment, verified on Windows Docker Desktop. Airflow
DAGs start paused, Jaeger traces are ephemeral, and the agent's Airflow connector
remains disabled under its HTTPS restriction. Local cleartext networking, Vite
preview and shared local role credentials are not production deployment controls.

See the [complete runbook and actual results](local/README.md),
[security controls](SECURITY.md), [database privilege policy](database/README.md)
and [security regression history](security/README.md).

GitHub Actions tests, Docker image security, SBOMs and verification limits:
[CI architecture and results](CI.md).
