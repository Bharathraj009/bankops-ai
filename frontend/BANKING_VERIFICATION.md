# Step 58 verification

Verified on 2026-10-15 (America/Chicago). Implementation changes are confined to
frontend/. Banking code, V1–V5, agent, Airflow and monitoring are unchanged. Migration
SHA-256 values match their pre-existing hashes.

## Automated results

| Check | Result |
| --- | --- |
| ESLint | Passed, zero warnings |
| TypeScript strict checks | Passed, including both Playwright configurations |
| Prettier | Passed |
| Vitest components/API mocks | 33 passed across two files |
| Desktop/mobile Chromium suite | 16 passed |
| Separate real-backend Chromium workflow | 1 passed |
| Banking Maven suite | 202 passed, zero failures/errors/skips |
| Production build | Passed |

The banking lazy chunk is approximately 5 KB gzip; the shared application chunk is
approximately 135 KB gzip. Backend output is in the ignored build artifact
../backend/banking-service/target/step58-tests.log.

Tests cover exact decimals, malformed input/responses, public-field allowlisting,
safe HTTP errors, zero-balance creation, account/history reads, pagination and
direction filters, confirmation cancellation, duplicate clicks, and explicit
same-key retries after uncertain failures. Chromium checks navigation, keyboard
access, themes, reduced motion and responsive layouts. Screenshots were inspected.

## Actual isolated API verification

Used postgres:17 container bankops-step58-tests on localhost:55458, Spring Boot
test profile on localhost:18058, and a separate Vite proxy on localhost:5174.
No development banking database writes were performed. The test profile disables
development funding and reserve bootstrap.

A unique source fixture received a legitimate $1,000 opening balance through an
INSERT under existing V3 rules. No direct balance UPDATE, trigger bypass or fake
ledger postings were used. The UI created the destination with zero balance.

| Request | Actual result |
| --- | --- |
| POST /api/v1/accounts through UI | 201, generated ID, USD, balance 0 |
| Source account/history GET | 200, balance 1000 |
| Confirm $250 transfer through UI | 201, COMPLETED, amount 250 |
| Explicit matching replay | 200, original transfer ID |
| Same key with amount 251 | 409, conflict rejected |
| Source refresh | 200, balance 750 |
| Destination lookup | 200, balance 250 |
| Source ledger-backed history | 200, OUTGOING, 250, COMPLETED |
| Destination ledger-backed history | 200, INCOMING, 250, COMPLETED |
| Uncaught Chromium page errors | None |

Final SQL reconciliation: six synthetic accounts, three completed transfers, six
ledger entries; total balances and total opening balances both $3,000; signed
ledger net $0.00; zero balance mismatches; zero lifecycle/posting mismatches.
Checks included debit/credit counts, matching amounts/currencies and account roles.
Flyway versions 1–5 were successful.

These totals include retained fixtures from two early browser-harness attempts.
Harness fixes supplied JSON Content-Type for replay, narrowed a locator to exclude
a closed dialog, and separated live artifacts after parallel Playwright invocations
collided. The final suites ran sequentially. Assertions were retained.

## Repeating the live test

The live test is outside the default *.spec.ts suite. It never runs automatically.
Use a fresh dedicated PostgreSQL database and a disposable password supplied through
environment variables. Never use the development database.

1. Start postgres:17 as bankops-step58-tests, database/user bankops_test, port
   127.0.0.1:55458:5432. Supply POSTGRES_PASSWORD from your temporary environment.
2. Build the existing banking jar with Java 25/Maven. Set SPRING_DATASOURCE_URL to
   jdbc:postgresql://localhost:55458/bankops_test; SPRING_DATASOURCE_USERNAME and
   BANKOPS_DB_USER to bankops_test; SPRING_DATASOURCE_PASSWORD and BANKOPS_DB_PASSWORD
   from the temporary password. Set SPRING_PROFILES_ACTIVE=test,
   SERVER_ADDRESS=127.0.0.1 and SERVER_PORT=18058. Start the jar from banking-service/.
3. After health is UP, create a unique fixture only in that isolated database:

```powershell
$fixture=[guid]::NewGuid().ToString()
docker exec bankops-step58-tests psql -U bankops_test -d bankops_test -c "INSERT INTO accounts(id,account_number,currency,balance) VALUES ('$fixture','STEP58-SOURCE-$fixture','USD',1000.00);"
```

4. Start a separate frontend server from frontend/:

```powershell
$env:BANKOPS_BANKING_API_TARGET='http://127.0.0.1:18058'
npx vite --host 127.0.0.1 --port 5174 --strictPort
```

5. In another frontend/ shell set BANKOPS_ISOLATED_SOURCE_ID to that fixture UUID,
   then explicitly opt in:

```powershell
$env:BANKOPS_ISOLATED_BANKING='step58-local-only'
npx playwright test --config playwright.live.config.ts
```

The test checks the unique fixture's exact account number and $1,000 balance before
any write. A misdirected proxy fails before creating an account. Use a new fixture
each run. No cleanup SQL deletes/truncates financial records.

## Limitations

There is no global account-list/search, global transfer history, raw ledger API or
backend authentication layer. Account search is session-scoped; history filters
are page-scoped and pagination is server-driven. Reads are independent snapshots.
Production requires an appropriate authenticated gateway and same-origin API proxy.

Retry keys/drafts remain in memory. In-app navigation preserves Banking state;
unresolved attempts guard navigation and prompt before reload/tab closure. Forcing
a reload discards the key. Investigate uncertain outcomes before creating another
transfer. Durable cross-session and cross-tab protection requires a future server
contract. No automatic financial write retry is implemented.

Temporary verification services are stopped after verification, retaining the
isolated database container and its data. Existing development services are left
running. See README.md for normal frontend setup and safety behavior.
