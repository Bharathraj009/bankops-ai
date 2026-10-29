package com.bankops.banking;

import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.SQLException;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import javax.sql.DataSource;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class IdempotencyIntegrationTests extends IsolatedPostgresTest {
    @Autowired DataSource dataSource;
    private record Request(String scope, String key, String hash, String source, String destination, String amount) {}
    private String id() { return UUID.randomUUID().toString(); }
    private void sql(Connection c, String command) throws SQLException {
        try (var s = c.createStatement()) { s.execute(command); }
    }
    private String account(Connection c) throws SQLException {
        String id = id();
        sql(c, "INSERT INTO accounts(id,account_number,balance) VALUES ('" + id + "','" + id + "',100)");
        return id;
    }
    private Request fixture() throws SQLException {
        try (var c = dataSource.getConnection()) {
            return new Request(id(), id(), "fingerprint-a", account(c), account(c), "10");
        }
    }
    private String create(Connection c, Request request) throws SQLException {
        try (var s = c.prepareStatement("SELECT create_idempotent_transfer(?,?,?,?::uuid,?::uuid,?::numeric,'USD')")) {
            s.setString(1, request.scope); s.setString(2, request.key); s.setString(3, request.hash);
            s.setString(4, request.source); s.setString(5, request.destination); s.setBigDecimal(6, new BigDecimal(request.amount));
            try (var r = s.executeQuery()) { assertTrue(r.next()); return r.getString(1); }
        }
    }
    private void complete(Connection c, Request request, String transfer) throws SQLException {
        sql(c, "INSERT INTO ledger_entries(id,transfer_id,account_id,entry_type,amount) VALUES ('"
            + id() + "','" + transfer + "','" + request.source + "','DEBIT'," + request.amount + "),('"
            + id() + "','" + transfer + "','" + request.destination + "','CREDIT'," + request.amount + ")");
        sql(c, "UPDATE transfers SET status='COMPLETED' WHERE id='" + transfer + "'");
    }
    private int count(Connection c, String table, String condition) throws SQLException {
        try (var s = c.createStatement(); var r = s.executeQuery("SELECT count(*) FROM " + table + " WHERE " + condition)) {
            assertTrue(r.next()); return r.getInt(1);
        }
    }
    private void balance(Connection c, String account, String expected) throws SQLException {
        try (var s = c.createStatement(); var r = s.executeQuery("SELECT balance FROM accounts WHERE id='" + account + "'")) {
            assertTrue(r.next()); assertEquals(new BigDecimal(expected), r.getBigDecimal(1));
        }
    }
    private void oneTransfer(Request request, String transfer, String status) throws SQLException {
        try (var c = dataSource.getConnection()) {
            assertEquals(1, count(c, "transfers", "source_account_id='" + request.source + "'"));
            assertEquals(1, count(c, "idempotency_records", "scope='" + request.scope + "' AND idempotency_key='" + request.key + "'"));
            try (var s = c.createStatement(); var r = s.executeQuery(
                "SELECT i.request_hash,i.transfer_id,t.status FROM idempotency_records i JOIN transfers t ON t.id=i.transfer_id "
                    + "WHERE i.scope='" + request.scope + "' AND i.idempotency_key='" + request.key + "'")) {
                assertTrue(r.next()); assertEquals(request.hash, r.getString(1));
                assertEquals(transfer, r.getString(2)); assertEquals(status, r.getString(3));
            }
            assertEquals(status.equals("COMPLETED") ? 2 : 0, count(c, "ledger_entries", "transfer_id='" + transfer + "'"));
            balance(c, request.source, status.equals("COMPLETED") ? "90.00" : "100.00");
            balance(c, request.destination, status.equals("COMPLETED") ? "110.00" : "100.00");
        }
    }

    @Test void matchingRetriesReturnOriginalPendingCompletedAndFailedTransfers() throws Exception {
        for (String state : new String[]{"PENDING", "COMPLETED", "FAILED"}) {
            var request = fixture(); String transfer;
            try (var c = dataSource.getConnection()) {
                c.setAutoCommit(false);
                transfer = create(c, request);
                assertEquals(transfer, create(c, request));
                if (state.equals("COMPLETED")) complete(c, request, transfer);
                if (state.equals("FAILED")) sql(c, "UPDATE transfers SET status='FAILED' WHERE id='" + transfer + "'");
                c.commit();
            }
            try (var c = dataSource.getConnection()) { assertEquals(transfer, create(c, request)); }
            oneTransfer(request, transfer, state);
        }
    }

    @Test void sameKeyInDifferentScopesCreatesIndependentTransfers() throws Exception {
        var request = fixture();
        var other = new Request(id(), request.key, "different-fingerprint", request.source, request.destination, "11");
        try (var c = dataSource.getConnection()) {
            String first = create(c, request), second = create(c, other);
            assertNotEquals(first, second);
            assertEquals(first, create(c, request)); assertEquals(second, create(c, other));
            assertEquals(2, count(c, "transfers", "source_account_id='" + request.source + "'"));
            assertEquals(2, count(c, "idempotency_records", "idempotency_key='" + request.key + "'"));
        }
    }

    @Test void conflictingFingerprintsAndDetailsAreRejectedWithoutCreatingTransfers() throws Exception {
        var request = fixture(); String transfer, other;
        try (var c = dataSource.getConnection()) { transfer = create(c, request); other = account(c); }
        for (var changed : new Request[]{
            new Request(request.scope, request.key, "fingerprint-b", request.source, request.destination, "10"),
            new Request(request.scope, request.key, request.hash, other, request.destination, "10"),
            new Request(request.scope, request.key, request.hash, request.source, other, "10"),
            new Request(request.scope, request.key, request.hash, request.source, request.destination, "11"),
            new Request(request.scope, request.key, request.hash, request.source, request.destination, "10.001")}) {
            try (var c = dataSource.getConnection()) {
                c.setAutoCommit(false);
                try { assertEquals("23514", assertThrows(SQLException.class, () -> create(c, changed)).getSQLState()); }
                finally { c.rollback(); }
            }
            oneTransfer(request, transfer, "PENDING");
        }
    }

    @Test void storedIdentityFingerprintAndAssignedTransferCannotChangeOrBeRemoved() throws Exception {
        var request = fixture(); String transfer, otherTransfer;
        try (var c = dataSource.getConnection()) {
            transfer = create(c, request);
            otherTransfer = create(c, new Request(request.scope, id(), request.hash, request.source, request.destination, "10"));
        }
        String where = "scope='" + request.scope + "' AND idempotency_key='" + request.key + "'";
        for (String assignment : new String[]{"request_hash='changed'", "scope='changed'", "idempotency_key='changed'",
            "id='" + id() + "'", "transfer_id=NULL", "transfer_id='" + otherTransfer + "'",
            "created_at=created_at+INTERVAL '1 second'"}) {
            try (var c = dataSource.getConnection()) {
                c.setAutoCommit(false);
                try { assertEquals("23514", assertThrows(SQLException.class, () -> sql(c,
                    "UPDATE idempotency_records SET " + assignment + " WHERE " + where)).getSQLState()); }
                finally { c.rollback(); }
            }
        }
        for (String command : new String[]{"DELETE FROM idempotency_records WHERE " + where, "TRUNCATE idempotency_records"}) {
            try (var c = dataSource.getConnection()) {
                c.setAutoCommit(false);
                try { assertEquals("23514", assertThrows(SQLException.class, () -> sql(c, command)).getSQLState()); }
                finally { c.rollback(); }
            }
        }
        try (var c = dataSource.getConnection()) {
            sql(c, "UPDATE idempotency_records SET request_hash=request_hash,transfer_id=transfer_id WHERE " + where);
            assertEquals(transfer, create(c, request));
            assertEquals(2, count(c, "transfers", "source_account_id='" + request.source + "'"));
        }
    }

    @Test void existingUnboundClaimCanBeBoundOnceWithMatchingFingerprint() throws Exception {
        var request = fixture();
        try (var c = dataSource.getConnection()) {
            sql(c, "INSERT INTO idempotency_records(id,scope,idempotency_key,request_hash) VALUES ('"
                + id() + "','" + request.scope + "','" + request.key + "','" + request.hash + "')");
            String transfer = create(c, request);
            assertEquals(transfer, create(c, request));
            oneTransfer(request, transfer, "PENDING");
        }
    }

    @Test void failedForeignKeyAndInsufficientFundsRollBackClaimAndTransfer() throws Exception {
        var request = fixture();
        try (var c = dataSource.getConnection()) {
            c.setAutoCommit(false);
            try {
                var invalid = new Request(request.scope, request.key, request.hash, id(), request.destination, "10");
                assertEquals("23503", assertThrows(SQLException.class, () -> create(c, invalid)).getSQLState());
            } finally { c.rollback(); }
            assertEquals(0, count(c, "idempotency_records", "scope='" + request.scope + "'"));
            var overdraft = new Request(request.scope, request.key, request.hash, request.source, request.destination, "101");
            String overdraftTransfer = create(c, overdraft);
            assertEquals("23514", assertThrows(SQLException.class, () -> complete(c, overdraft, overdraftTransfer)).getSQLState());
            c.rollback();
            assertEquals(0, count(c, "idempotency_records", "scope='" + request.scope + "'"));
            assertEquals(0, count(c, "transfers", "source_account_id='" + request.source + "'"));
            String transfer = create(c, request);
            c.commit();
            oneTransfer(request, transfer, "PENDING");
        }
    }

    private void concurrentRetry(boolean rollbackFirst, boolean differentHash, boolean differentDetails) throws Exception {
        var request = fixture();
        var retry = new Request(request.scope, request.key, differentHash ? "fingerprint-b" : request.hash,
            request.source, request.destination, differentDetails ? "11" : request.amount);
        var started = new CountDownLatch(1);
        String first;
        try (var executor = Executors.newSingleThreadExecutor(); var c = dataSource.getConnection()) {
            c.setAutoCommit(false);
            try {
                first = create(c, request);
                if (!rollbackFirst) complete(c, request, first);
                var result = executor.submit(() -> {
                    try (var other = dataSource.getConnection()) {
                        other.setAutoCommit(false);
                        sql(other, "SET LOCAL lock_timeout='5s'");
                        started.countDown();
                        try {
                            String transfer = create(other, retry);
                            other.commit();
                            return transfer;
                        } catch (SQLException error) {
                            other.rollback();
                            return error.getSQLState();
                        }
                    }
                });
                assertTrue(started.await(5, TimeUnit.SECONDS));
                assertThrows(TimeoutException.class, () -> result.get(200, TimeUnit.MILLISECONDS));
                if (rollbackFirst) c.rollback(); else c.commit();
                String outcome = result.get(10, TimeUnit.SECONDS);
                if (differentHash || differentDetails) {
                    assertEquals("23514", outcome);
                    oneTransfer(request, first, "COMPLETED");
                } else if (rollbackFirst) {
                    assertNotEquals(first, outcome);
                    oneTransfer(request, outcome, "PENDING");
                } else {
                    assertEquals(first, outcome);
                    oneTransfer(request, first, "COMPLETED");
                }
            } finally { c.rollback(); }
        }
    }

    @Test void concurrentMatchingRequestsCreateOneTransferAndMoveMoneyOnce() throws Exception {
        concurrentRetry(false, false, false);
    }
    @Test void concurrentDifferentFingerprintIsRejected() throws Exception {
        concurrentRetry(false, true, false);
    }
    @Test void concurrentDifferentDetailsWithSameFingerprintAreRejected() throws Exception {
        concurrentRetry(false, false, true);
    }
    @Test void concurrentRetryTakesOverRolledBackClaimWithoutAnOrphanTransfer() throws Exception {
        concurrentRetry(true, false, false);
    }

    @Test void v5PreservesExistingV4ClaimAndCompletedTransfer() throws Exception {
        String schema = "idempotency_upgrade_" + id().replace("-", "");
        String url = System.getenv("BANKOPS_TEST_DB_URL"), user = System.getenv("BANKOPS_TEST_DB_USER"), password = System.getenv("BANKOPS_TEST_DB_PASSWORD");
        try {
            Flyway.configure().dataSource(url, user, password).schemas(schema).defaultSchema(schema).target("4").load().migrate();
            Request request; String transfer = id();
            try (var c = java.sql.DriverManager.getConnection(url, user, password)) {
                c.setSchema(schema); c.setAutoCommit(false);
                request = new Request(id(), id(), "legacy-fingerprint", account(c), account(c), "10");
                sql(c, "INSERT INTO transfers(id,source_account_id,destination_account_id,amount) VALUES ('"
                    + transfer + "','" + request.source + "','" + request.destination + "',10)");
                complete(c, request, transfer);
                sql(c, "INSERT INTO idempotency_records(id,scope,idempotency_key,request_hash,transfer_id) VALUES ('"
                    + id() + "','" + request.scope + "','" + request.key + "','" + request.hash + "','" + transfer + "')");
                c.commit();
            }
            var v5 = Flyway.configure().dataSource(url, user, password).schemas(schema).defaultSchema(schema).target("5").load();
            v5.migrate(); v5.validate();
            assertEquals("5", v5.info().current().getVersion().toString());
            try (var c = java.sql.DriverManager.getConnection(url, user, password)) {
                c.setSchema(schema);
                assertEquals(transfer, create(c, request));
                assertEquals(1, count(c, "transfers", "source_account_id='" + request.source + "'"));
                assertEquals(2, count(c, "ledger_entries", "transfer_id='" + transfer + "'"));
                balance(c, request.source, "90.00"); balance(c, request.destination, "110.00");
            }
        } finally {
            try (var c = java.sql.DriverManager.getConnection(url, user, password)) { sql(c, "DROP SCHEMA IF EXISTS " + schema + " CASCADE"); }
        }
    }
}
