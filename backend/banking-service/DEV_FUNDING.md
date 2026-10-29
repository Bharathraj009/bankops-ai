`POST /api/v1/dev/accounts/{accountId}/fund` exists only when `dev` is active and
none of `prod`, `production`, or `test` is active. Both the controller and funding
service use this exclusion. Default, production and test profiles have no route;
activating `dev` alongside production or test does not enable it.

Set `BANKOPS_DEV_FUNDING_ACCOUNT_ID` to a stable UUID for the dedicated USD system
account. To initialize it on dev startup, explicitly set
`BANKOPS_DEV_RESERVE_BOOTSTRAP_ENABLED=true`. The finite initial reserve defaults
to 1000000.00 USD; override with `BANKOPS_DEV_RESERVE_INITIAL_BALANCE` if needed.
Bootstrap is disabled by default and absent in production/test, even if enabled
through configuration. It runs after Flyway via an application runner.

Initialization performs one account INSERT with that opening balance. V3's
existing INSERT trigger derives the immutable `opening_balance`; its deferred
check validates the resulting balance. This is the schema's supported genesis
baseline, not a transfer: there is no external account from which to debit initial
money, so inventing ledger postings would misrepresent it. No trigger is disabled,
no existing balance is updated, and no synthetic ledger entry is created.

The account number is `DEV-FUNDING-<configured UUID>`. Repeated or concurrent
initialization retains the existing account and current balance, including after
funding has depleted it. An incompatible existing account or changed initial
balance fails startup without modifying existing data. Keep the configured UUID
stable; choosing a new UUID intentionally provisions a different reserve.
Initialization and deferred-constraint checks are transactional. No migration is
needed. The application never replenishes or resets the reserve.

With bootstrap disabled, an already provisioned compatible system account may
still be configured for funding. Missing/invalid configuration or a
missing reserve account returns safe 503 `FUNDING_UNAVAILABLE`. No migration is
needed; V1–V5 remain intact.

Send `Idempotency-Key` (nonblank, at most 255 characters) and `{"amount":10.25}`.
Only positive USD amounts with at most 17 integer digits and two decimal places
are accepted. The system account cannot fund itself; clients cannot specify the
source, currency, status, or balances. Unknown targets return 404, invalid input
400, conflicting key reuse 409, and exhausted reserve or target overflow 422.

Funding calls the same transactional execution path as ordinary transfers, using
the separate scope `POST:/api/v1/dev/accounts/fund`. It debits the system account
and credits the target with balanced immutable ledger postings. Only V3's triggers
move balances. First execution returns 201 with the transfer DTO; matching retries
return 200 with the original result. Failures roll back claims, transfers, postings
and balance changes, including deferred commit failures. This is redistribution
of a finite test reserve, not money creation or a production funding mechanism.

Integration tests provision a reserve solely in disposable PostgreSQL fixtures,
send real HTTP requests under `dev`, verify retries/concurrency/rollback, and
start isolated application instances for default, prod, production, test and
mixed profiles to verify that the funding beans and route are absent.
