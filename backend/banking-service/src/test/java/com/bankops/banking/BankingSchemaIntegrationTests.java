package com.bankops.banking;

import java.sql.Connection;
import java.sql.SQLException;
import java.util.UUID;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class BankingSchemaIntegrationTests extends IsolatedPostgresTest {
    @Autowired DataSource dataSource;

    private String id() { return UUID.randomUUID().toString(); }
    private void sql(Connection c, String sql) throws SQLException {
        try (var statement = c.createStatement()) { statement.execute(sql); }
    }
    private String account(Connection c) throws SQLException {
        String id = id();
        sql(c, "INSERT INTO accounts(id, account_number, balance) VALUES ('" + id + "','" + id + "',100.00)");
        return id;
    }
    private String transfer(Connection c, String source, String destination) throws SQLException {
        return transfer(c, source, destination, "10.00");
    }
    private String transfer(Connection c, String source, String destination, String amount) throws SQLException {
        String id = id();
        sql(c, "INSERT INTO transfers(id,source_account_id,destination_account_id,amount) VALUES ('"
            + id + "','" + source + "','" + destination + "'," + amount + ")");
        return id;
    }
    private void posting(Connection c, String transfer, String account, String type, String amount) throws SQLException {
        sql(c, "INSERT INTO ledger_entries(id,transfer_id,account_id,entry_type,amount) VALUES ('"
            + id() + "','" + transfer + "','" + account + "','" + type + "'," + amount + ")");
    }
    private void rejects(String state, String command) throws Exception {
        try (var c = dataSource.getConnection()) {
            c.setAutoCommit(false);
            try {
                assertEquals(state, assertThrows(SQLException.class, () -> sql(c, command)).getSQLState());
            } finally { c.rollback(); }
        }
    }
    @Test void accountConstraints() throws Exception {
        rejects("23514", "INSERT INTO accounts(id,account_number,currency,balance,created_at) VALUES ('" + id() + "','" + id() + "','USD',-0.01,DEFAULT)");
        rejects("23514", "INSERT INTO accounts(id,account_number,currency,balance,created_at) VALUES ('" + id() + "','" + id() + "','EUR',0,DEFAULT)");
        rejects("23514", "INSERT INTO accounts(id,account_number,currency,balance,created_at) VALUES ('" + id() + "','" + id() + "','USD','NaN',DEFAULT)");
        try (var c = dataSource.getConnection()) {
            c.setAutoCommit(false);
            try {
                String a = account(c);
                assertEquals("23505", assertThrows(SQLException.class, () -> sql(c,
                    "INSERT INTO accounts(id,account_number) VALUES ('" + id() + "','" + a + "')")).getSQLState());
            } finally { c.rollback(); }
        }
    }
    @Test void transferAndPostingConstraints() throws Exception {
        rejects("23503", "INSERT INTO transfers(id,source_account_id,destination_account_id,amount) VALUES ('"
            + id() + "','" + id() + "','" + id() + "',10)");
        for (String assignment : new String[]{"amount=0", "amount=-1", "amount='NaN'", "currency='EUR'", "status='UNKNOWN'", "destination_account_id=source_account_id"}) {
            try (var c = dataSource.getConnection()) {
                c.setAutoCommit(false);
                try {
                    String t = transfer(c, account(c), account(c));
                    assertEquals("23514", assertThrows(SQLException.class, () -> sql(c,
                        "UPDATE transfers SET " + assignment + " WHERE id='" + t + "'")).getSQLState());
                } finally { c.rollback(); }
            }
        }
        for (String assignment : new String[]{"amount=0", "currency='EUR'", "entry_type='OTHER'", "account_id='" + id() + "'", "transfer_id='" + id() + "'"}) {
            try (var c = dataSource.getConnection()) {
                c.setAutoCommit(false);
                try {
                    String a = account(c), b = account(c), t = transfer(c, a, b);
                    String values = "SELECT '" + id() + "'::uuid, id, source_account_id, 'DEBIT', 10, 'USD', CURRENT_TIMESTAMP FROM transfers WHERE id='" + t + "'";
                    sql(c, "CREATE TEMP TABLE candidate (LIKE ledger_entries INCLUDING DEFAULTS) ON COMMIT DROP");
                    sql(c, "INSERT INTO candidate " + values);
                    sql(c, "UPDATE candidate SET " + assignment);
                    String expected = assignment.startsWith("account_id") || assignment.startsWith("transfer_id") ? "23503" : "23514";
                    assertEquals(expected, assertThrows(SQLException.class, () -> sql(c,
                        "INSERT INTO ledger_entries SELECT * FROM candidate")).getSQLState());
                } finally { c.rollback(); }
            }
        }
    }
    @Test void balancedCompletionAndExactMoney() throws Exception {
        try (var c = dataSource.getConnection()) {
            c.setAutoCommit(false);
            try {
                String a = account(c), b = account(c), t = transfer(c, a, b, "0.10+0.20");
                posting(c, t, a, "DEBIT", "0.30");
                posting(c, t, b, "CREDIT", "0.30");
                sql(c, "UPDATE transfers SET status='COMPLETED' WHERE id='" + t + "'");
                sql(c, "SET CONSTRAINTS ALL IMMEDIATE");
                try (var s = c.createStatement(); var r = s.executeQuery("SELECT balance FROM accounts WHERE id='" + b + "'")) {
                    assertTrue(r.next());
                    assertEquals(new java.math.BigDecimal("100.30"), r.getBigDecimal(1));
                }
            } finally { c.rollback(); }
        }
    }
    @Test void invalidLedgerRejectedAtCommit() throws Exception {
        for (String scenario : new String[]{"missing", "one-sided", "unbalanced", "wrong-amount", "wrong-account", "failed"}) {
            try (var c = dataSource.getConnection()) {
                c.setAutoCommit(false);
                try {
                    String a = account(c), b = account(c), t = transfer(c, a, b);
                    if (!scenario.equals("missing")) {
                        posting(c, t, scenario.equals("wrong-account") ? b : a, "DEBIT", scenario.equals("wrong-amount") ? "5" : "10");
                        if (!scenario.equals("one-sided")) posting(c, t, b, "CREDIT", scenario.equals("unbalanced") || scenario.equals("wrong-amount") ? "5" : "10");
                    }
                    if (!scenario.equals("one-sided")) sql(c, "UPDATE transfers SET status='" + (scenario.equals("failed") ? "FAILED" : "COMPLETED") + "' WHERE id='" + t + "'");
                    assertEquals("23514", assertThrows(SQLException.class, c::commit, scenario).getSQLState());
                } finally { c.rollback(); }
            }
        }
    }
    @Test void ledgerIsImmutableAndPostingIsUnique() throws Exception {
        for (String action : new String[]{"UPDATE ledger_entries SET amount=11", "DELETE FROM ledger_entries", "TRUNCATE ledger_entries", "duplicate"}) {
            try (var c = dataSource.getConnection()) {
                c.setAutoCommit(false);
                try {
                    String a = account(c), b = account(c), t = transfer(c, a, b);
                    posting(c, t, a, "DEBIT", "10");
                    posting(c, t, b, "CREDIT", "10");
                    sql(c, "SET CONSTRAINTS ALL IMMEDIATE");
                    assertEquals(action.equals("duplicate") ? "23505" : "23514", assertThrows(SQLException.class, () -> {
                        if (action.equals("duplicate")) posting(c, t, a, "DEBIT", "10");
                        else sql(c, action + (action.startsWith("TRUNCATE") ? "" : " WHERE transfer_id='" + t + "'"));
                    }).getSQLState());
                } finally { c.rollback(); }
            }
        }
    }
    @Test void idempotencyKeysAreScoped() throws Exception {
        try (var c = dataSource.getConnection()) {
            c.setAutoCommit(false);
            try {
                String key = id();
                for (String scope : new String[]{"scope-a", "scope-b"}) sql(c,
                    "INSERT INTO idempotency_records(id,scope,idempotency_key,request_hash) VALUES ('" + id() + "','" + scope + "','" + key + "','hash')");
                sql(c, "SET CONSTRAINTS ALL IMMEDIATE");
                assertEquals("23505", assertThrows(SQLException.class, () -> sql(c,
                    "INSERT INTO idempotency_records(id,scope,idempotency_key,request_hash) VALUES ('" + id() + "','scope-a','" + key + "','hash')")).getSQLState());
            } finally { c.rollback(); }
        }
        rejects("23503", "INSERT INTO idempotency_records(id,scope,idempotency_key,request_hash,transfer_id) VALUES ('" + id() + "','scope','key','hash','" + id() + "')");
    }

    private void balance(Connection c, String account, String expected) throws SQLException {
        try (var s = c.createStatement(); var r = s.executeQuery("SELECT balance FROM accounts WHERE id='" + account + "'")) {
            assertTrue(r.next());
            assertEquals(new java.math.BigDecimal(expected), r.getBigDecimal(1));
        }
    }

    @Test void committedTransferMovesMoneyExactlyOnce() throws Exception {
        String a, b, t;
        try (var c = dataSource.getConnection()) {
            c.setAutoCommit(false);
            a = account(c); b = account(c); t = transfer(c, a, b);
            posting(c, t, a, "DEBIT", "10");
            posting(c, t, b, "CREDIT", "10");
            sql(c, "UPDATE transfers SET status='COMPLETED' WHERE id='" + t + "'");
            c.commit();
        }
        try (var c = dataSource.getConnection()) {
            balance(c, a, "90.00"); balance(c, b, "110.00");
            sql(c, "UPDATE transfers SET status='COMPLETED' WHERE id='" + t + "'");
            balance(c, a, "90.00"); balance(c, b, "110.00");
            try (var s = c.createStatement(); var r = s.executeQuery("SELECT count(*), sum(CASE WHEN entry_type='DEBIT' THEN -amount ELSE amount END) FROM ledger_entries WHERE transfer_id='" + t + "'")) {
                assertTrue(r.next()); assertEquals(2, r.getInt(1));
                assertEquals(0, r.getBigDecimal(2).signum());
            }
        }
    }

    @Test void invalidCompletionRollsBackPostingsAndBalances() throws Exception {
        String a, b, t;
        try (var c = dataSource.getConnection()) {
            a = account(c); b = account(c); t = transfer(c, a, b);
            c.setAutoCommit(false);
            posting(c, t, a, "DEBIT", "10");
            posting(c, t, b, "CREDIT", "5");
            sql(c, "UPDATE transfers SET status='COMPLETED' WHERE id='" + t + "'");
            assertEquals("23514", assertThrows(SQLException.class, c::commit).getSQLState());
            c.rollback();
        }
        try (var c = dataSource.getConnection()) {
            balance(c, a, "100.00"); balance(c, b, "100.00");
            try (var s = c.createStatement(); var r = s.executeQuery("SELECT status, (SELECT count(*) FROM ledger_entries WHERE transfer_id='" + t + "') FROM transfers WHERE id='" + t + "'")) {
                assertTrue(r.next()); assertEquals("PENDING", r.getString(1)); assertEquals(0, r.getInt(2));
            }
        }
    }

    @Test void insufficientFundsRollsBackEvenWhenCreditComesFirst() throws Exception {
        String a, b, t;
        try (var c = dataSource.getConnection()) {
            a = account(c); b = account(c); t = transfer(c, a, b, "101");
            c.setAutoCommit(false);
            posting(c, t, b, "CREDIT", "101");
            assertEquals("23514", assertThrows(SQLException.class, () -> posting(c, t, a, "DEBIT", "101")).getSQLState());
            c.rollback();
        }
        try (var c = dataSource.getConnection()) {
            balance(c, a, "100.00"); balance(c, b, "100.00");
            try (var s = c.createStatement(); var r = s.executeQuery("SELECT count(*) FROM ledger_entries WHERE transfer_id='" + t + "'")) {
                assertTrue(r.next()); assertEquals(0, r.getInt(1));
            }
        }
    }

    @Test void balanceCannotBeOverwrittenAfterPosting() throws Exception {
        try (var c = dataSource.getConnection()) {
            c.setAutoCommit(false);
            try {
                String a = account(c), b = account(c), t = transfer(c, a, b);
                posting(c, t, a, "DEBIT", "10"); posting(c, t, b, "CREDIT", "10");
                sql(c, "UPDATE transfers SET status='COMPLETED' WHERE id='" + t + "'");
                sql(c, "UPDATE accounts SET balance=100 WHERE id='" + a + "'");
                assertEquals("23514", assertThrows(SQLException.class, c::commit).getSQLState());
            } finally { c.rollback(); }
        }
    }

    @Test void concurrentDebitsCannotSpendTheSameFunds() throws Exception {
        String a, b, first, second;
        try (var c = dataSource.getConnection()) {
            a = account(c); b = account(c);
            first = transfer(c, a, b, "80"); second = transfer(c, a, b, "80");
        }
        var started = new java.util.concurrent.CountDownLatch(1);
        try (var executor = java.util.concurrent.Executors.newSingleThreadExecutor();
             var c = dataSource.getConnection()) {
            c.setAutoCommit(false);
            try {
                posting(c, first, a, "DEBIT", "80"); posting(c, first, b, "CREDIT", "80");
                sql(c, "UPDATE transfers SET status='COMPLETED' WHERE id='" + first + "'");
                var result = executor.submit(() -> {
                    try (var other = dataSource.getConnection()) {
                        other.setAutoCommit(false);
                        sql(other, "SET LOCAL lock_timeout='5s'");
                        try {
                            started.countDown();
                            return assertThrows(SQLException.class, () -> posting(other, second, a, "DEBIT", "80")).getSQLState();
                        } finally { other.rollback(); }
                    }
                });
                assertTrue(started.await(5, java.util.concurrent.TimeUnit.SECONDS));
                assertThrows(java.util.concurrent.TimeoutException.class,
                    () -> result.get(200, java.util.concurrent.TimeUnit.MILLISECONDS));
                c.commit();
                assertEquals("23514", result.get(10, java.util.concurrent.TimeUnit.SECONDS));
            } finally { c.rollback(); }
        }
        try (var c = dataSource.getConnection()) {
            balance(c, a, "20.00"); balance(c, b, "180.00");
        }
    }

    @Test void v3RefusesToBlessUnreconciledV2Postings() throws Exception {
        String schema = "legacy_" + id().replace("-", "");
        String url = System.getenv("BANKOPS_TEST_DB_URL");
        String user = System.getenv("BANKOPS_TEST_DB_USER");
        String password = System.getenv("BANKOPS_TEST_DB_PASSWORD");
        var v2 = org.flywaydb.core.Flyway.configure().dataSource(url, user, password)
            .schemas(schema).defaultSchema(schema).target("2").load();
        try {
            v2.migrate();
            try (var c = java.sql.DriverManager.getConnection(url, user, password)) {
                c.setSchema(schema);
                c.setAutoCommit(false);
                String a = account(c), b = account(c), t = transfer(c, a, b);
                posting(c, t, a, "DEBIT", "10"); posting(c, t, b, "CREDIT", "10");
                sql(c, "UPDATE transfers SET status='COMPLETED' WHERE id='" + t + "'");
                c.commit();
                balance(c, a, "100.00"); balance(c, b, "100.00");
            }
            var v3 = org.flywaydb.core.Flyway.configure().dataSource(url, user, password)
                .schemas(schema).defaultSchema(schema).target("3").load();
            var error = assertThrows(org.flywaydb.core.api.FlywayException.class, v3::migrate);
            assertTrue(error.getMessage().contains("Reconcile V2 ledger entries"));
            assertEquals("2", v3.info().current().getVersion().toString());
        } finally {
            try (var c = java.sql.DriverManager.getConnection(url, user, password)) {
                sql(c, "DROP SCHEMA IF EXISTS " + schema + " CASCADE");
            }
        }
    }
}
