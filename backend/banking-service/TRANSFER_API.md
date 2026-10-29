`POST /api/v1/transfers` requires an `Idempotency-Key` header (nonblank, at most
255 characters) and this JSON body:

```json
{"sourceAccountId":"<UUID>","destinationAccountId":"<different UUID>","amount":10.25}
```

Amounts must be positive USD values with at most 17 integer digits and two decimal
places. Currency is fixed to USD. Other fields, including client IDs, statuses,
balances, and currencies, are rejected. Keys are scoped to `POST:/api/v1/transfers`.
Fingerprints use server-generated SHA-256 over canonical account IDs, USD, and an
amount normalized to two decimals, so `10`, `10.0`, and `10.00` are matching requests.

The service locks both accounts in UUID order before claiming the key through V5.
It posts one debit and one credit, lets V3 update balances, and completes the
transfer in one transaction. V2's deferred ledger/balance checks and V4's lifecycle
checks remain active. A response is sent only after commit. No migration is needed.

Newly executed transfers return 201. Matching terminal retries return 200 with the
original transfer (`id`, `sourceAccountId`, `destinationAccountId`, `amount`,
`currency`, `status`, `createdAt`) and never move money again. Previously committed
balanced PENDING postings are completed without being posted twice.

Validation errors return 400; unknown accounts 404; conflicting key reuse 409;
insufficient funds or destination balance overflow 422. Database failures return
safe 500/503 responses without SQL details. Unsuccessful execution rolls back the
claim, transfer, postings, and balance changes; it does not store a FAILED result.
Transient failures can be retried with the same key. There is no authentication
layer yet; key scope is endpoint-wide rather than per user.

HTTP integration tests use disposable PostgreSQL and random server ports, including
duplicate and conflicting concurrent requests, overspending, opposite-direction
transfers, and rollback at posting and deferred-commit stages. Run `mvnw.cmd test`
with the same `BANKOPS_TEST_DB_*` variables described in ACCOUNT_API.md.

`GET /api/v1/transfers/{transferId}` returns HTTP 200 with the public transfer
representation listed above, for PENDING, COMPLETED, or FAILED transfers. It does
not require an idempotency header and never returns stored keys or fingerprints.
The lookup uses a read-only transaction and an ordinary parameterized SELECT
without row locks, returning committed data. Unknown IDs return 404 with
`TRANSFER_NOT_FOUND`; malformed UUIDs return 400 with `INVALID_TRANSFER_ID`.
