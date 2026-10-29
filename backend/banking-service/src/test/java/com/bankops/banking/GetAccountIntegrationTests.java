package com.bankops.banking;

import java.math.BigDecimal;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.UUID;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class GetAccountIntegrationTests extends IsolatedPostgresTest {
    @Value("${local.server.port}") int port;
    @Autowired DataSource dataSource;
    @Autowired ObjectMapper mapper;
    private final HttpClient http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build();

    private HttpResponse<String> get(String id) throws Exception {
        return http.send(operatorRequest(URI.create("http://localhost:" + port + "/api/v1/accounts/" + id))
            .timeout(Duration.ofSeconds(10)).GET().build(), HttpResponse.BodyHandlers.ofString());
    }
    private JsonNode created() throws Exception {
        String number = "get-api-" + UUID.randomUUID();
        var response = http.send(operatorRequest(URI.create("http://localhost:" + port + "/api/v1/accounts"))
            .timeout(Duration.ofSeconds(10)).header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString("{\"accountNumber\":\"" + number + "\"}")).build(),
            HttpResponse.BodyHandlers.ofString());
        assertEquals(201, response.statusCode(), response.body());
        return mapper.readTree(response.body());
    }
    private String counts() throws Exception {
        try (var c = dataSource.getConnection(); var s = c.createStatement(); var r = s.executeQuery("""
            SELECT (SELECT count(*) FROM accounts),(SELECT count(*) FROM transfers),
                (SELECT count(*) FROM ledger_entries),(SELECT count(*) FROM idempotency_records)
            """)) {
            assertTrue(r.next()); return r.getLong(1) + ":" + r.getLong(2) + ":" + r.getLong(3) + ":" + r.getLong(4);
        }
    }
    private void assertBalance(UUID id, String expected) throws Exception {
        var response = get(id.toString());
        assertEquals(200, response.statusCode(), response.body());
        var account = mapper.readTree(response.body());
        assertEquals(id.toString(), account.get("id").asString());
        assertEquals("USD", account.get("currency").asString());
        assertEquals(0, new BigDecimal(expected).compareTo(account.get("balance").decimalValue()));
        assertEquals(5, account.size()); // Reuses the existing public DTO, including createdAt.
        assertFalse(account.has("openingBalance")); assertFalse(account.has("ledgerEntries"));
    }

    @Test void returnsCreatedAccountWithoutWritingOrExposingInternalFields() throws Exception {
        var created = created();
        String before = counts();
        for (int i = 0; i < 2; i++) {
            var response = get(created.get("id").asString());
            assertEquals(200, response.statusCode(), response.body());
            assertTrue(response.headers().firstValue("Content-Type").orElse("").startsWith("application/json"));
            assertEquals(created, mapper.readTree(response.body()));
        }
        assertEquals(before, counts());
        assertBalance(UUID.fromString(created.get("id").asString()), "0.00");
        try (var c = dataSource.getConnection(); var s = c.prepareStatement("SELECT balance,opening_balance FROM accounts WHERE id=?")) {
            s.setObject(1, UUID.fromString(created.get("id").asString()));
            try (var r = s.executeQuery()) {
                assertTrue(r.next()); assertEquals(new BigDecimal("0.00"), r.getBigDecimal(1));
                assertEquals(new BigDecimal("0.00"), r.getBigDecimal(2));
            }
        }
    }

    @Test void unknownAccountsReturnSafe404WithoutWrites() throws Exception {
        String before = counts();
        for (String id : new String[]{UUID.randomUUID().toString(), "00000000-0000-0000-0000-000000000000"}) {
            var response = get(id);
            assertEquals(404, response.statusCode(), response.body());
            var error = mapper.readTree(response.body());
            assertEquals("ACCOUNT_NOT_FOUND", error.get("code").asString());
            assertEquals("Account not found", error.get("message").asString());
            assertFalse(response.body().contains(id)); assertFalse(response.body().contains("SELECT"));
            assertFalse(response.body().contains("Exception")); assertFalse(response.body().contains("jdbc"));
        }
        assertEquals(before, counts());
    }

    @Test void malformedIdsReturnSafe400WithoutWrites() throws Exception {
        String before = counts();
        for (String id : new String[]{"private-invalid-id", "123", "ffffffff-ffff-ffff-ffff-fffffffffffz"}) {
            var response = get(id);
            assertEquals(400, response.statusCode(), response.body());
            assertEquals("INVALID_ACCOUNT_ID", mapper.readTree(response.body()).get("code").asString());
            assertFalse(response.body().contains(id)); assertFalse(response.body().contains("Exception"));
        }
        assertEquals(before, counts());
    }

    @Test void readsCommittedLedgerBalancesAndNeverExposesUncommittedMoneyMovement() throws Exception {
        var destinationResponse = created();
        UUID source = UUID.randomUUID(), destination = UUID.fromString(destinationResponse.get("id").asString());
        try (var c = dataSource.getConnection()) {
            try (var s = c.prepareStatement("INSERT INTO accounts(id,account_number,balance) VALUES (?,?,100)")) {
                s.setObject(1, source); s.setString(2, source.toString()); s.executeUpdate();
            }
            c.setAutoCommit(false);
            try {
                UUID transfer;
                try (var s = c.prepareStatement("SELECT create_idempotent_transfer(?,'get-balance','fingerprint',?,?,10)")) {
                    s.setString(1, UUID.randomUUID().toString()); s.setObject(2, source); s.setObject(3, destination);
                    try (var r = s.executeQuery()) { assertTrue(r.next()); transfer = r.getObject(1, UUID.class); }
                }
                try (var s = c.prepareStatement("""
                    INSERT INTO ledger_entries(id,transfer_id,account_id,entry_type,amount)
                    VALUES (?,?,?,'DEBIT',10),(?,?,?,'CREDIT',10)
                    """)) {
                    s.setObject(1, UUID.randomUUID()); s.setObject(2, transfer); s.setObject(3, source);
                    s.setObject(4, UUID.randomUUID()); s.setObject(5, transfer); s.setObject(6, destination); s.executeUpdate();
                }
                try (var s = c.prepareStatement("UPDATE transfers SET status='COMPLETED' WHERE id=?")) {
                    s.setObject(1, transfer); s.executeUpdate();
                }
                assertBalance(source, "100.00"); assertBalance(destination, "0.00");
                c.commit();
                String before = counts();
                assertBalance(source, "90.00"); assertBalance(destination, "10.00");
                assertEquals(before, counts());
                try (var s = c.prepareStatement("SELECT count(*),sum(CASE WHEN entry_type='DEBIT' THEN -amount ELSE amount END) FROM ledger_entries WHERE transfer_id=?")) {
                    s.setObject(1, transfer);
                    try (var r = s.executeQuery()) { assertTrue(r.next()); assertEquals(2, r.getInt(1)); assertEquals(0, r.getBigDecimal(2).signum()); }
                }
            } finally { c.rollback(); }
        }
    }

    @Test void uncommittedAndRolledBackAccountsRemainUnknown() throws Exception {
        UUID id = UUID.randomUUID();
        String before = counts();
        try (var c = dataSource.getConnection()) {
            c.setAutoCommit(false);
            try (var s = c.prepareStatement("INSERT INTO accounts(id,account_number,balance) VALUES (?,?,0)")) {
                s.setObject(1, id); s.setString(2, id.toString()); s.executeUpdate();
                assertEquals(404, get(id.toString()).statusCode());
            } finally { c.rollback(); }
        }
        assertEquals(404, get(id.toString()).statusCode()); assertEquals(before, counts());
    }
}
