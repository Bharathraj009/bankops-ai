# Public repository scope

The public repository is [Bharathraj009/bankops-ai](https://github.com/Bharathraj009/bankops-ai).
The implementation baseline was committed and pushed as `8dff277` on `main`.
See [publication status](PUBLICATION_READINESS.md) and
[hosted verification](docs/verification/HOSTED_BASELINE.md).

This checkout has separate sanitized public history. Development Git objects,
private banking responses, credentials, dumps, logs, caches, installed dependencies
and raw generated test/scan evidence are excluded. Ignored `.publication/` outputs
are private review aids and must never be committed.

The project demonstrates banking integrity, observability, read-only reconciliation,
manual investigation, local retrieval and human approval boundaries. It uses
synthetic test data and is not production banking software. Cloud inference was
tested only with mocked transports. Inference and remediation remain disabled by
default; operational financial evidence cannot be exported to cloud providers.

[Dated verification records](docs/verification/README.md) preserve preparation and
implementation evidence. Earlier pending-publication statements describe their
recorded dates. The screenshot is a static UI preview with no service requests or
banking records, not evidence of a live incident.

This follow-up quality review makes local changes only. Commit and push require
explicit approval; no history rewrite is proposed.
