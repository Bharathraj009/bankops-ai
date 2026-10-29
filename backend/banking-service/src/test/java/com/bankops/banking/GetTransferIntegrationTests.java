package com.bankops.banking;

import java.math.BigDecimal;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.UUID;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import tools.jackson.databind.ObjectMapper;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class GetTransferIntegrationTests extends IsolatedPostgresTest {
    @Value("${local.server.port}") int port;
    @Autowired DataSource dataSource;
    @Autowired ObjectMapper mapper;
    private final HttpClient http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build();
    private record Fixture(UUID id, UUID source, UUID destination, String key) {}

    private HttpResponse<String> get(String id) throws Exception {
        return http.send(operatorRequest(URI.create("http://localhost:" + port + "/api/v1/transfers/" + id))
            .timeout(Duration.ofSeconds(10)).GET().build(), HttpResponse.BodyHandlers.ofString());
    }
    private Fixture fixture() throws Exception {
        UUID source = UUID.randomUUID(), destination = UUID.randomUUID();
        String key = "PRIVATE_KEY_" + UUID.randomUUID();
        try (var c = dataSource.getConnection()) {
            c.setAutoCommit(false);
            try (var s = c.prepareStatement("INSERT INTO accounts(id,account_number,balance) VALUES (?,?,100),(?,?,0)")) {
                s.setObject(1, source); s.setString(2, source.toString());
                s.setObject(3, destination); s.setString(4, destination.toString()); s.executeUpdate();
            }
            UUID id;
            try (var s = c.prepareStatement("SELECT create_idempotent_transfer('get-transfer-probe',?,'PRIVATE_FINGERPRINT',?,?,10.25)")) {
                s.setString(1, key); s.setObject(2, source); s.setObject(3, destination);
                try (var r = s.executeQuery()) { assertTrue(r.next()); id = r.getObject(1, UUID.class); }
            }
            c.commit(); return new Fixture(id, source, destination, key);
        }
    }
    private void complete(java.sql.Connection c, Fixture t) throws Exception {
        try (var s = c.prepareStatement("""
            INSERT INTO ledger_entries(id,transfer_id,account_id,entry_type,amount)
            VALUES (?,?,?,'DEBIT',10.25),(?,?,?,'CREDIT',10.25)
            """)) {
            s.setObject(1, UUID.randomUUID()); s.setObject(2, t.id); s.setObject(3, t.source);
            s.setObject(4, UUID.randomUUID()); s.setObject(5, t.id); s.setObject(6, t.destination); s.executeUpdate();
        }
        try (var s = c.prepareStatement("UPDATE transfers SET status='COMPLETED' WHERE id=?")) {
            s.setObject(1, t.id); s.executeUpdate();
        }
    }
    private String snapshot(Fixture t) throws Exception {
        try (var c = dataSource.getConnection(); var s = c.prepareStatement("""
            SELECT json_build_object(
                'transfer',(SELECT row_to_json(t) FROM transfers t WHERE id=?),
                'accounts',(SELECT json_agg(a ORDER BY id) FROM accounts a WHERE id IN (?,?)),
                'ledger',(SELECT json_agg(l ORDER BY id) FROM ledger_entries l WHERE transfer_id=?),
                'idempotency',(SELECT json_agg(i ORDER BY id) FROM idempotency_records i WHERE transfer_id=?))
            """)) {
            s.setObject(1, t.id); s.setObject(2, t.source); s.setObject(3, t.destination);
            s.setObject(4, t.id); s.setObject(5, t.id);
            try (var r = s.executeQuery()) { assertTrue(r.next()); return r.getString(1); }
        }
    }
    private void assertTransfer(Fixture t, String status) throws Exception {
        var response = get(t.id.toString());
        assertEquals(200, response.statusCode(), response.body());
        var json = mapper.readTree(response.body());
        assertEquals(7, json.size());
        assertEquals(t.id.toString(), json.get("id").asString());
        assertEquals(t.source.toString(), json.get("sourceAccountId").asString());
        assertEquals(t.destination.toString(), json.get("destinationAccountId").asString());
        assertEquals(0, new BigDecimal("10.25").compareTo(json.get("amount").decimalValue()));
        assertEquals("USD", json.get("currency").asString()); assertEquals(status, json.get("status").asString());
        var timestamp = OffsetDateTime.parse(json.get("createdAt").asString());
        try (var c = dataSource.getConnection(); var s = c.prepareStatement("SELECT created_at FROM transfers WHERE id=?")) {
            s.setObject(1, t.id);
            try (var r = s.executeQuery()) { assertTrue(r.next()); assertEquals(timestamp.toInstant(), r.getObject(1, OffsetDateTime.class).toInstant()); }
        }
        assertFalse(response.body().contains(t.key)); assertFalse(response.body().contains("PRIVATE_FINGERPRINT"));
        assertFalse(json.has("idempotencyKey")); assertFalse(json.has("requestHash")); assertFalse(json.has("ledgerEntries"));
    }

    @Test void readsAllLifecycleStatesWithoutChangingFinancialOrIdempotencyData() throws Exception {
        for (String status : new String[]{"PENDING", "COMPLETED", "FAILED"}) {
            var t = fixture();
            if (!status.equals("PENDING")) {
                try (var c = dataSource.getConnection()) {
                    c.setAutoCommit(false);
                    if (status.equals("COMPLETED")) complete(c, t);
                    else try (var s = c.prepareStatement("UPDATE transfers SET status='FAILED' WHERE id=?")) { s.setObject(1,t.id); s.executeUpdate(); }
                    c.commit();
                }
            }
            String before = snapshot(t);
            assertTransfer(t, status); assertTransfer(t, status);
            assertEquals(before, snapshot(t));
        }
    }

    @Test void retrievesTransferCreatedThroughPostWithoutRequiringAnIdempotencyHeader() throws Exception {
        var t = fixture(); String key = UUID.randomUUID().toString();
        var request = operatorRequest(URI.create("http://localhost:"+port+"/api/v1/transfers"))
            .timeout(Duration.ofSeconds(10)).header("Content-Type","application/json").header("Idempotency-Key",key)
            .POST(HttpRequest.BodyPublishers.ofString("{\"sourceAccountId\":\""+t.source+"\",\"destinationAccountId\":\""+t.destination+"\",\"amount\":10.25}")).build();
        var post = http.send(request, HttpResponse.BodyHandlers.ofString()); assertEquals(201,post.statusCode(),post.body());
        var created = mapper.readTree(post.body());
        var response = get(created.get("id").asString()); assertEquals(200,response.statusCode(),response.body());
        assertEquals(created,mapper.readTree(response.body())); assertFalse(response.body().contains(key));
    }

    @Test void unknownIdsReturnSafe404() throws Exception {
        for (String id : new String[]{UUID.randomUUID().toString(),"00000000-0000-0000-0000-000000000000"}) {
            var response = get(id); assertEquals(404,response.statusCode(),response.body());
            var error = mapper.readTree(response.body());
            assertEquals("TRANSFER_NOT_FOUND",error.get("code").asString()); assertEquals("Transfer not found",error.get("message").asString());
            assertFalse(response.body().contains(id)); assertFalse(response.body().contains("SELECT")); assertFalse(response.body().contains("Exception"));
        }
    }

    @Test void malformedUuidsReturnSafe400() throws Exception {
        for (String id : new String[]{"PRIVATE_INVALID_UUID","123","ffffffff-ffff-ffff-ffff-fffffffffffz"}) {
            var response = get(id); assertEquals(400,response.statusCode(),response.body());
            assertEquals("INVALID_TRANSFER_ID",mapper.readTree(response.body()).get("code").asString());
            assertFalse(response.body().contains(id)); assertFalse(response.body().contains("Exception"));
        }
    }

    @Test void lookupDoesNotLockTransferOrExposeUncommittedCompletion() throws Exception {
        var t = fixture(); String before = snapshot(t);
        try (var c = dataSource.getConnection()) {
            c.setAutoCommit(false);
            try {
                complete(c,t); // Holds the transfer row lock and uncommitted postings.
                assertTransfer(t,"PENDING"); assertEquals(before,snapshot(t));
            } finally { c.rollback(); }
        }
        assertTransfer(t,"PENDING"); assertEquals(before,snapshot(t));
    }
}
