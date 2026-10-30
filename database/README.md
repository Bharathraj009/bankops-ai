# Database identities and least privilege

## Unified local Docker integration (Step 67)

Use [local/compose.yaml](../local/compose.yaml) and the
[local runbook](../local/README.md) for the complete fresh local platform.
Its one-shot prepare and grant adapter imports this directory's reviewed functions;
the packaged migration launcher runs as `bankops_migrator`, sharing only the new
PostgreSQL container's loopback network namespace. The host CLI remote-target
guards are unchanged. Applications receive only runtime credentials, while
Airflow retains SELECT-only reconciliation access. There are no external volume
references and neither database publishes a host port.

Verified 2026-10-28: prepare/migrate/grant succeeded, repeat Flyway validation
succeeded, restricted banking startup was healthy, reconciliation passed and an
actual Airflow write attempt was denied even after selecting a read-write
transaction. The financial snapshot stayed identical. The unified stack starts
with an empty ledger; populated financial regressions ran separately against a
disposable PostgreSQL 17 fixture (219 banking and 57 Airflow/database tests passed).
V1–V6 were not edited. No legacy development role/volume rollout was performed.

Environment-specific roles/ACLs are provisioned outside Flyway. **V1–V6 are
unchanged; no V7 is needed.** These tools contain no financial DML, account-owner
backfill, trigger bypass, destructive cleanup or automatic ownership transfer.
The new policy has been verified on disposable databases, not rolled out to
existing development volumes. See [SECURITY.md](../SECURITY.md) for actual results.

## Roles

| Principal | Banking database access |
| --- | --- |
| `bankops` administrator | Infrastructure bootstrap/backup only; not an application credential |
| `bankops_migrator` | CONNECT, public schema CREATE/USAGE; owns objects it creates through Flyway; no superuser/database/role creation or memberships |
| `bankops_runtime` | CONNECT/USAGE, SELECT on seven application tables; narrowly scoped INSERT/UPDATE columns and V5 keyed-transfer function only |
| `bankops_reconciliation` | CONNECT/USAGE and SELECT only on accounts, transfers, ledger entries and Flyway history |
| `bankops_agent` / `bankops_monitoring` | NOLOGIN, no CONNECT, schema, table or function permissions; services receive no banking credentials |

Runtime grants: INSERT on account identity/currency/balance, transfer request
fields, ledger postings, idempotency claim fields, customer registration fields,
session creation fields and ownership account/customer IDs. UPDATE is limited to
`accounts.balance` (required by the **invoker** ledger trigger), `transfers.status`,
idempotency `request_hash`/`transfer_id` (required by V5 matching conflict claims)
and session `revoked_at`. No DELETE, TRUNCATE, TRIGGER, REFERENCES, schema CREATE,
role membership, Flyway history or unrestricted column UPDATE is granted.
Existing V3/V4/V5/V6 triggers continue enforcing financial and ownership rules.

Account INSERT balance is needed for the existing dev reserve's genesis creation
and zero-balance account API. This is not a new restriction on SQL-level genesis;
the trusted runtime can create accounts with opening balances. Customer APIs
still force zero. A separate bootstrap-only database privilege would require a
reviewed change to that existing behavior and is outside this step.

## Fresh local environment procedure

Use a new explicitly selected local database or a reviewed backup/restore clone.
Supply distinct administrator, migration, runtime and reconciliation secrets via
environment variables/your secret manager. [.env.example](.env.example) lists names
only; Python does not automatically read it. Do not copy placeholder values.
`BANKOPS_DB_ADMIN_DSN` must specify a local host and match `BANKOPS_DB_NAME`.
Provisioning is superuser-only infrastructure work; applications never receive it.

1. Start PostgreSQL only after configuring its separate
   `BANKOPS_POSTGRES_ADMIN_PASSWORD`. Compose retains the existing data volume.
   Never delete/reinitialize a volume to apply these settings. The banking HBA
   policy uses SCRAM for sockets/IPv4/IPv6 and restricts application/migration/
   reconciliation connections to the `bankops` database. Unknown roles are denied.
2. Install `database/requirements.txt` in a separate tooling environment (or use
   the existing Airflow environment with psycopg). From the repository root,
   with the three service passwords and admin DSN in the tool environment:

   ```powershell
   $env:BANKOPS_DB_SECURITY_APPLY='local-only'
   python database/provision.py prepare
   ```

   This creates bounded roles, revokes public CONNECT/TEMP/schema CREATE, sets
   safe search paths and removes default public function execution. Service
   passwords must be distinct, printable ASCII, 32–256 characters. Python sends
   salted SCRAM verifiers, never plaintext passwords, to PostgreSQL. Repeat
   prepare verifies existing SCRAM credentials without rotating them; mismatches
   abort and roll back. Unexpected privileged roles, memberships or runtime-owned
   objects require a separate reviewed rollout, not automatic repair.
3. Build the banking JAR using its normal Maven build. In a **separate process
   environment containing only migration credentials**, from `backend/banking-service`:

   ```powershell
   $env:BANKOPS_MIGRATION_APPLY='local-only'
   & "$env:JAVA_HOME/bin/java.exe" '-Dloader.main=com.bankops.banking.security.DatabaseMigration' `
     -cp target/banking-service-0.0.1-SNAPSHOT.jar org.springframework.boot.loader.launch.PropertiesLauncher
   ```

   Set `BANKOPS_MIGRATION_DB_URL`, `BANKOPS_MIGRATION_DB_USER=bankops_migrator`
   and `BANKOPS_MIGRATION_DB_PASSWORD` in that environment first. The launcher
   requires an explicit local JDBC target and the non-superuser migration role.
   It performs Flyway migrate/validate with clean disabled, suppresses sensitive
   provider diagnostics and never starts Spring's HTTP server. It is disabled
   without opt-in. Do not use it against a legacy database before the review below.
4. In the administrator tooling environment, after successful migration:

   ```powershell
   python database/provision.py grant
   ```

   Requires successful V1–V6 history. It resets table **and column** grants, removes
   public function execution and applies the explicit permission matrix. Reapply
   after reviewed future migrations; new tables/functions are private by default.
5. Start normal banking with only runtime credentials (`BANKOPS_DB_USER`,
   `BANKOPS_DB_PASSWORD`, optional `BANKOPS_DB_URL`) and the existing API secrets:

   ```powershell
   ./mvnw.cmd spring-boot:run '-Dspring-boot.run.profiles=dev,db-secure'
   ```

   The normal configuration disables embedded Flyway by default. A startup
   verifier rejects superusers, owner/DDL privileges, memberships, unsafe function
   exposure, Flyway history access and other elevated capabilities. `db-secure`
   also selects the runtime username default and explicitly disables Flyway.
   Do not pass administrator/migration passwords to this process. Existing local
   configurations using `bankops` now **fail closed** until securely provisioned.

## Existing volumes and rollback planning

No existing development grants, credentials, object ownership or banking rows
were changed. The audited banking database still has V1–V5 financial tables owned
by the legacy superuser. V6 was previously verified only in test schemas. A new
migration principal cannot automatically take over that history/table ownership.
Back up and verify restore, inspect historical ledger compatibility and review a
specific metadata/object-ownership handoff before applying migrations/grants to
that database. These tools deliberately do not run `REASSIGN OWNED`, alter existing
table owners or grant a migrator membership in a superuser role. No unsafe
fallback to administrator credentials is provided. Preserve a verified backup
and an explicitly reviewed ACL/credential rollback plan; never roll back by
deleting accounts, tables, volumes or Flyway history.

PostgreSQL image `POSTGRES_*` init settings **do not rotate existing passwords**.
The HBA mount/server settings take effect only when the service is deliberately
recreated; they were not applied to the existing volume during this task. Do not
assume changing dotenv values has changed a database role password.

Airflow metadata is a different PostgreSQL cluster. Fresh volumes use the separate
`airflow_admin` infrastructure secret and an `airflow` non-superuser owning only
its metadata database. Standalone Airflow needs metadata DDL for its own migrations.
The initializer cannot upgrade an existing metadata volume; plan that role
handoff separately. The runtime receives no metadata administrator secret. Banking
reconciliation continues using only `bankops_reconciliation`. The agent uses HTTP
evidence and separate SQLite approvals, and monitoring uses HTTP/its own storage.

## Tests and limits

`DatabasePermissionsIntegrationTests` creates a disposable database, uses actual
Flyway migration ownership and runs real HTTP financial operations with the
restricted runtime. Its write/DDL denial probes never target development data.
`database/tests` covers provisioning/privacy; `database/integration` requires
`BANKOPS_DATABASE_SECURITY_TEST_DSN` selecting disposable PostgreSQL. The three
`verify_*.py` scripts require `BANKOPS_DB_SECURITY_TEST=step65-disposable` and use
fixed Step 65 containers only, never user-configurable live targets.

PostgreSQL ACLs cannot constrain a compromised superuser or distinguish individual
customers sharing the trusted runtime role. Customer ownership remains enforced
by Spring services and immutable V6 metadata, not row-level security. Local
Compose uses SCRAM without TLS inside a trusted single-host Docker environment.
Nonlocal deployment needs separately managed TLS (`sslmode=verify-full`), HBA,
secret rotation, backup policies and network controls. PostgreSQL diagnostics are
restricted to avoid SQL/credential leakage; maintain privacy-safe operational
monitoring for failures. No production deployment is authorized by these tests.
