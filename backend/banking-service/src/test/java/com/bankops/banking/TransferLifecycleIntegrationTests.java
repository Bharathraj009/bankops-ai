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
class TransferLifecycleIntegrationTests extends IsolatedPostgresTest {
    @Autowired DataSource dataSource;

    private record Transfer(String id, String source, String destination) {}
    private String id() { return UUID.randomUUID().toString(); }

    private void sql(Connection c, String command) throws SQLException {
        try (var s = c.createStatement()) { s.execute(command); }
    }

    private String account(Connection c) throws SQLException {
        String id = id();
        sql(c, "INSERT INTO accounts(id,account_number,balance) VALUES ('" + id + "','" + id + "',100)");
        return id;
    }

    private Transfer pending(Connection c) throws SQLException {
        var t = new Transfer(id(), account(c), account(c));
        sql(c, "INSERT INTO transfers(id,source_account_id,destination_account_id,amount) VALUES ('"
            + t.id + "','" + t.source + "','" + t.destination + "',10)");
        return t;
    }

    private void status(Connection c, Transfer t, String status) throws SQLException {
        sql(c, "UPDATE transfers SET status='" + status + "' WHERE id='" + t.id + "'");
    }

    private void postings(Connection c, Transfer t) throws SQLException {
        for (String type : new String[]{"DEBIT", "CREDIT"}) {
            String account = type.equals("DEBIT") ? t.source : t.destination;
            sql(c, "INSERT INTO ledger_entries(id,transfer_id,account_id,entry_type,amount) VALUES ('"
                + id() + "','" + t.id + "','" + account + "','" + type + "',10)");
        }
    }

    private Transfer committed(String status) throws SQLException {
        try (var c = dataSource.getConnection()) {
            c.setAutoCommit(false);
            var t = pending(c);
            if (status.equals("COMPLETED")) postings(c, t);
            status(c, t, status);
            c.commit();
            return t;
        }
    }

    private void assertTransfer(Connection c, Transfer t, String status) throws SQLException {
        try (var s = c.createStatement(); var r = s.executeQuery(
            "SELECT status,amount,source_account_id,destination_account_id FROM transfers WHERE id='" + t.id + "'")) {
            assertTrue(r.next());
            assertEquals(status, r.getString(1));
            assertEquals(new BigDecimal("10.00"), r.getBigDecimal(2));
            assertEquals(t.source, r.getString(3)); assertEquals(t.destination, r.getString(4));
        }
        try (var s = c.createStatement(); var r = s.executeQuery(
            "SELECT count(*),coalesce(sum(CASE WHEN entry_type='DEBIT' THEN -amount ELSE amount END),0) "
                + "FROM ledger_entries WHERE transfer_id='" + t.id + "'")) {
            assertTrue(r.next()); assertEquals(status.equals("COMPLETED") ? 2 : 0, r.getInt(1));
            assertEquals(0, r.getBigDecimal(2).signum());
        }
        for (String account : new String[]{t.source, t.destination}) {
            String expected = status.equals("COMPLETED") ? (account.equals(t.source) ? "90.00" : "110.00") : "100.00";
            try (var s = c.createStatement(); var r = s.executeQuery("SELECT balance FROM accounts WHERE id='" + account + "'")) {
                assertTrue(r.next()); assertEquals(new BigDecimal(expected), r.getBigDecimal(1));
            }
        }
    }

    @Test void transfersMustStartPending() throws Exception {
        var t = committed("PENDING");
        for (String terminal : new String[]{"COMPLETED", "FAILED"}) {
            try (var c = dataSource.getConnection()) {
                c.setAutoCommit(false);
                try {
                    var error = assertThrows(SQLException.class, () -> sql(c,
                        "INSERT INTO transfers(id,source_account_id,destination_account_id,amount,status) VALUES ('"
                            + id() + "','" + t.source + "','" + t.destination + "',10,'" + terminal + "')"));
                    assertEquals("23514", error.getSQLState());
                    assertTrue(error.getMessage().contains("must start PENDING"));
                } finally { c.rollback(); }
            }
        }
        try (var c = dataSource.getConnection()) { assertTransfer(c, t, "PENDING"); }
    }

    @Test void completionCommitsWithPostingsInEitherOrderAndAllowsRetries() throws Exception {
        for (boolean completeFirst : new boolean[]{false, true}) {
            var t = committed("PENDING");
            try (var c = dataSource.getConnection()) {
                c.setAutoCommit(false);
                if (completeFirst) status(c, t, "COMPLETED");
                postings(c, t);
                if (!completeFirst) status(c, t, "COMPLETED");
                c.commit();
                status(c, t, "COMPLETED"); // A retry must not move money again.
                c.commit();
            }
            try (var c = dataSource.getConnection()) { assertTransfer(c, t, "COMPLETED"); }
        }
    }

    @Test void failureCommitsWithoutPostingsAndAllowsRetries() throws Exception {
        var t = committed("PENDING");
        try (var c = dataSource.getConnection()) {
            c.setAutoCommit(false);
            status(c, t, "PENDING");
            status(c, t, "FAILED");
            c.commit();
            status(c, t, "FAILED");
            c.commit();
        }
        try (var c = dataSource.getConnection()) { assertTransfer(c, t, "FAILED"); }
    }

    @Test void terminalStatesCannotBeReopenedOrSwitched() throws Exception {
        for (String terminal : new String[]{"COMPLETED", "FAILED"}) {
            var t = committed(terminal);
            for (String next : new String[]{"PENDING", "COMPLETED", "FAILED"}) {
                if (next.equals(terminal)) continue;
                try (var c = dataSource.getConnection()) {
                    c.setAutoCommit(false);
                    try {
                        assertEquals("23514", assertThrows(SQLException.class, () -> status(c, t, next)).getSQLState());
                    } finally { c.rollback(); }
                    assertTransfer(c, t, terminal);
                }
            }
        }
    }

    @Test void transferTermsAreImmutableInEveryState() throws Exception {
        for (String state : new String[]{"PENDING", "COMPLETED", "FAILED"}) {
            var t = committed(state);
            String other;
            try (var c = dataSource.getConnection()) { other = account(c); }
            for (String assignment : new String[]{"amount=11", "source_account_id='" + other + "'",
                    "destination_account_id='" + other + "'", "id='" + id() + "'", "currency='EUR'"}) {
                try (var c = dataSource.getConnection()) {
                    c.setAutoCommit(false);
                    try {
                        var error = assertThrows(SQLException.class, () -> sql(c,
                            "UPDATE transfers SET " + assignment + " WHERE id='" + t.id + "'"));
                        assertEquals("23514", error.getSQLState());
                        assertTrue(error.getMessage().contains("immutable"));
                    } finally { c.rollback(); }
                    assertTransfer(c, t, state);
                }
            }
            try (var c = dataSource.getConnection()) {
                sql(c, "UPDATE transfers SET amount=amount,source_account_id=source_account_id,"
                    + "destination_account_id=destination_account_id WHERE id='" + t.id + "'");
                assertTransfer(c, t, state);
            }
        }
    }

    @Test void invalidTerminalLedgerRollsBackStatePostingsAndBalances() throws Exception {
        // COMPLETED without postings and FAILED with postings must both fail at commit.
        for (String terminal : new String[]{"COMPLETED", "FAILED"}) {
            var t = committed("PENDING");
            try (var c = dataSource.getConnection()) {
                c.setAutoCommit(false);
                try {
                    status(c, t, terminal);
                    if (terminal.equals("FAILED")) postings(c, t);
                    assertEquals("23514", assertThrows(SQLException.class, c::commit).getSQLState());
                } finally { c.rollback(); }
            }
            try (var c = dataSource.getConnection()) { assertTransfer(c, t, "PENDING"); }
        }
        var failed = committed("FAILED");
        try (var c = dataSource.getConnection()) {
            c.setAutoCommit(false);
            try {
                postings(c, failed);
                assertEquals("23514", assertThrows(SQLException.class, c::commit).getSQLState());
            } finally { c.rollback(); }
        }
        try (var c = dataSource.getConnection()) { assertTransfer(c, failed, "FAILED"); }
    }

    @Test void deletionAndTruncationCannotBypassTerminalStates() throws Exception {
        for (String terminal : new String[]{"COMPLETED", "FAILED"}) {
            var t = committed(terminal);
            for (String command : new String[]{"DELETE FROM transfers WHERE id='" + t.id + "'", "TRUNCATE transfers CASCADE"}) {
                try (var c = dataSource.getConnection()) {
                    c.setAutoCommit(false);
                    try {
                        assertEquals("23514", assertThrows(SQLException.class, () -> sql(c, command)).getSQLState());
                    } finally { c.rollback(); }
                    assertTransfer(c, t, terminal);
                }
            }
        }
    }

    @Test void concurrentCompletionAndFailureCannotBothSucceed() throws Exception {
        var t = committed("PENDING");
        var started = new CountDownLatch(1);
        try (var executor = Executors.newSingleThreadExecutor(); var c = dataSource.getConnection()) {
            c.setAutoCommit(false);
            try {
                postings(c, t);
                status(c, t, "COMPLETED");
                var result = executor.submit(() -> {
                    try (var other = dataSource.getConnection()) {
                        other.setAutoCommit(false);
                        sql(other, "SET LOCAL lock_timeout='5s'");
                        try {
                            started.countDown();
                            return assertThrows(SQLException.class, () -> status(other, t, "FAILED")).getSQLState();
                        } finally { other.rollback(); }
                    }
                });
                assertTrue(started.await(5, TimeUnit.SECONDS));
                assertThrows(TimeoutException.class, () -> result.get(200, TimeUnit.MILLISECONDS));
                c.commit();
                assertEquals("23514", result.get(10, TimeUnit.SECONDS));
            } finally { c.rollback(); }
        }
        try (var c = dataSource.getConnection()) { assertTransfer(c, t, "COMPLETED"); }
    }

    @Test void v4UpgradesExistingV3TransfersWithoutChangingMoneyOrHistory() throws Exception {
        String schema = "upgrade_" + id().replace("-", "");
        String url = System.getenv("BANKOPS_TEST_DB_URL");
        String user = System.getenv("BANKOPS_TEST_DB_USER");
        String password = System.getenv("BANKOPS_TEST_DB_PASSWORD");
        try {
            Flyway.configure().dataSource(url, user, password).schemas(schema).defaultSchema(schema).target("3").load().migrate();
            Transfer pending, completed, failed;
            try (var c = java.sql.DriverManager.getConnection(url, user, password)) {
                c.setSchema(schema); c.setAutoCommit(false);
                pending = pending(c); completed = pending(c); failed = pending(c);
                postings(c, completed); status(c, completed, "COMPLETED"); status(c, failed, "FAILED");
                c.commit();
            }
            var v4 = Flyway.configure().dataSource(url, user, password).schemas(schema).defaultSchema(schema).target("4").load();
            v4.migrate(); v4.validate();
            assertEquals("4", v4.info().current().getVersion().toString());
            try (var c = java.sql.DriverManager.getConnection(url, user, password)) {
                c.setSchema(schema);
                assertTransfer(c, pending, "PENDING"); assertTransfer(c, completed, "COMPLETED"); assertTransfer(c, failed, "FAILED");
                assertEquals("23514", assertThrows(SQLException.class, () -> status(c, failed, "PENDING")).getSQLState());
                status(c, pending, "FAILED");
                assertTransfer(c, pending, "FAILED");
            }
        } finally {
            try (var c = java.sql.DriverManager.getConnection(url, user, password)) {
                sql(c, "DROP SCHEMA IF EXISTS " + schema + " CASCADE");
            }
        }
    }
}
