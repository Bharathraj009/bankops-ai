# Reconlith development notes

This narrative follows dated, published verification records. It is not a reconstructed
commit history. The public repository began with sanitized source and has four commits
at the reviewed baseline 2f26908; those commits are not a complete development history.
Milestone numbers identify work recorded in reports, not releases or separate public commits.
No author dates or history are changed by this documentation.

| Recorded date | Milestone and design evolution | Public evidence |
| --- | --- | --- |
| 2026-10-15 | Human review became a separate persistent workflow: proposer/reviewer roles, terminal decisions and atomic audit records. Approval itself performed no execution. | [Approval verification and boundaries](../agent/APPROVALS.md) |
| 2026-10-29 | Image remediation separated build tooling from runtime dependencies and preserved strict gates. Startup testing exposed the missing async PostgreSQL driver, demonstrating why imports alone were insufficient. Remaining HIGH findings stayed disclosed. | [Step 71B closeout](../security/STEP71B_CLOSEOUT.md), [startup failure analysis](../CI.md#actual-verification-and-intermediate-failures) |
| 2026-10-29 | Step 73 separated retained development-service checks from isolated financial/security fixtures and documented image differences. | [Step 73](verification/STEP73_E2E_REPORT.md) |
| 2026-10-29 | Step 73B repaired a test-transport mismatch between httpx and production httpx2; provider calls remained mocked. Citation rejection was tested locally. | [Step 73B](verification/STEP73B_RAG_REPORT.md) |
| 2026-10-29 | Step 74 connected synthetic investigation slices while explicitly retaining the full-stack integration gap. | [Step 74](verification/STEP74_INTEGRATION_REPORT.md) |
| 2026-10-29 | Step 75 closed the scheduled reconciliation-to-dashboard gap for one disposable evidence-gap scenario. It added reconciliation runbook grounding and citation viewing while preserving partial evidence and disabled inference. | [Step 75](verification/STEP75_INTEGRATION_REPORT.md) |
| 2026-10-30 | Publication review clarified setup, architecture and historical evidence. Hosted application CI passed; five image gates remained blocked in the documentation baseline. | [Quality review](verification/QUALITY_AUDIT_2026-10-30.md), [hosted results](verification/HOSTED_36A88E8.md) |

## Technical evolution and traceability

The current source preserves the progression from ledger invariants to
operator-facing investigation. The following ordering is visible in migration
versions and component reports; it does not assign unverified development dates.

- **Ledger and transactions:** the
  [migration series](../backend/banking-service/src/main/resources/db/migration/)
  layers ledger constraints, balance consistency, lifecycle checks and scoped
  idempotency. V3 refuses to silently accept pre-existing postings without
  reconciliation; it makes a migration failure boundary explicit.
- **Concurrency and retries:**
  [ordered account locks and posting SQL](../backend/banking-service/src/main/java/com/bankops/banking/transfer/TransferRepository.java)
  work with [concurrent HTTP regressions](../backend/banking-service/src/test/java/com/bankops/banking/TransferApiIntegrationTests.java)
  to cover duplicate requests, overspending and opposite-direction transfers.
- **Observability:** [tracing verification dated 2026-10-15](../TRACING.md)
  records trace hierarchy, correlation/privacy tests and failure isolation. It
  also records connection-pool exhaustion found during testing and the test-pool
  correction, rather than presenting the first attempt as a pass.
- **Investigation:** [the graph record dated 2026-10-15](../agent/WORKFLOW.md)
  introduces the explicit two-branch join and bounded optional analysis stage.
  Later Step 73B/74/75 reports distinguish mocked inference, synthetic browser
  slices and the actual scheduled reconciliation path.
- **Reconciliation and retrieval:** Step 75 ties scheduler-created unavailable
  evidence to a specific reviewed runbook and visible citation. It preserves
  Undetermined RCA rather than manufacturing hypotheses from retrieval matches.

The progression is from integrity enforcement, through independent observation,
to bounded investigation and explicit review. Tests exposed setup and transport
failures as well as successful paths; the reports preserve those limits.

Remaining work includes the [planned demo](../README.md#planned-90-second-hybrid-demo),
production identity/TLS and credential lifecycle, rotating log capture, fuller
traffic evidence, vulnerability remediation and separately verified live inference.
These items are not represented as implemented production capabilities. See
[engineering decisions](ENGINEERING_DECISIONS.md) and [verification scope](VERIFICATION_EVIDENCE.md).

## Public name and preserved identifiers

Reconlith is the current presentation name. Historical BankOps AI report titles,
commit subjects and screenshot text remain traceable to their recorded evidence.
Java packages, Python modules, database/Docker names, environment variables, API
paths, workflows, directories, remotes and existing repository URLs keep their
technical names. Older component runbooks retain their original context; this
four-file documentation update does not imply an application UI rebrand.
