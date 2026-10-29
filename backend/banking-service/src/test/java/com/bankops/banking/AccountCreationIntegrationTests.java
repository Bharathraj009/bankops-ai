package com.bankops.banking;

import java.math.BigDecimal;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class AccountCreationIntegrationTests extends IsolatedPostgresTest {
    @Value("${local.server.port}") int port;
    @Autowired DataSource dataSource;
    @Autowired ObjectMapper mapper;
    private final HttpClient http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build();

    private String number() { return "api-" + UUID.randomUUID(); }
    private HttpRequest request(String body) {
        return operatorRequest(URI.create("http://localhost:" + port + "/api/v1/accounts"))
            .timeout(Duration.ofSeconds(15)).header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(body)).build();
    }
    private HttpResponse<String> post(String body) throws Exception {
        return http.send(request(body), HttpResponse.BodyHandlers.ofString());
    }
    private String body(String accountNumber) { return "{\"accountNumber\":\"" + accountNumber + "\",\"currency\":\"USD\"}"; }
    private long countAccounts() throws Exception {
        try (var c = dataSource.getConnection(); var s = c.createStatement(); var r = s.executeQuery("SELECT count(*) FROM accounts")) {
            assertTrue(r.next()); return r.getLong(1);
        }
    }
    private long countNumber(String number) throws Exception {
        try (var c = dataSource.getConnection(); var s = c.prepareStatement("SELECT count(*) FROM accounts WHERE account_number=?")) {
            s.setString(1, number);
            try (var r = s.executeQuery()) { assertTrue(r.next()); return r.getLong(1); }
        }
    }
    private void assertStoredZeroAccount(JsonNode response, String number) throws Exception {
        UUID id = UUID.fromString(response.get("id").asString());
        assertEquals(number, response.get("accountNumber").asString());
        assertEquals("USD", response.get("currency").asString());
        assertEquals(0, response.get("balance").decimalValue().signum());
        var createdAt = OffsetDateTime.parse(response.get("createdAt").asString());
        try (var c = dataSource.getConnection(); var s = c.prepareStatement("""
            SELECT account_number,currency,balance,opening_balance,created_at,
                (SELECT count(*) FROM ledger_entries WHERE account_id=accounts.id) AS postings
            FROM accounts WHERE id=?
            """)) {
            s.setObject(1, id);
            try (var r = s.executeQuery()) {
                assertTrue(r.next()); assertEquals(number, r.getString("account_number"));
                assertEquals("USD", r.getString("currency"));
                assertEquals(new BigDecimal("0.00"), r.getBigDecimal("balance"));
                assertEquals(new BigDecimal("0.00"), r.getBigDecimal("opening_balance"));
                assertEquals(createdAt.toInstant(), r.getObject("created_at", OffsetDateTime.class).toInstant());
                assertEquals(0, r.getInt("postings")); assertFalse(r.next());
            }
        }
    }

    @Test void createsAccountWithServerIdAndZeroOpeningBalance() throws Exception {
        String number = number();
        var response = post(body(number));
        assertEquals(201, response.statusCode(), response.body());
        assertTrue(response.headers().firstValue("Content-Type").orElse("").startsWith("application/json"));
        assertStoredZeroAccount(mapper.readTree(response.body()), number);
    }

    @Test void omittedCurrencyUsesSchemaUsdDefaultAndNumbersRespectMaximumLength() throws Exception {
        String number = "api-" + UUID.randomUUID().toString().replace("-", "") + "x".repeat(28);
        assertEquals(64, number.length());
        var response = post("{\"accountNumber\":\"" + number + "\"}");
        assertEquals(201, response.statusCode(), response.body());
        assertStoredZeroAccount(mapper.readTree(response.body()), number);
    }

    @Test void invalidAccountDetailsDoNotCreateAccounts() throws Exception {
        long before = countAccounts();
        for (String body : new String[]{"{}", "{\"accountNumber\":null}", "{\"accountNumber\":\"\"}",
            "{\"accountNumber\":\"   \"}", "{\"accountNumber\":\"" + "x".repeat(65) + "\"}",
            "{\"accountNumber\":\"" + number() + "\",\"currency\":\"EUR\"}",
            "{\"accountNumber\":\"" + number() + "\",\"currency\":\"usd\"}",
            "{\"accountNumber\":\"" + number() + "\",\"currency\":\"\"}"}) {
            var response = post(body);
            assertEquals(400, response.statusCode(), response.body());
            assertEquals("VALIDATION_ERROR", mapper.readTree(response.body()).get("code").asString());
        }
        assertEquals(before, countAccounts());
    }

    @Test void rejectsClientBalancesIdsTimestampsAndUnsupportedHolderFields() throws Exception {
        long before = countAccounts();
        for (String field : new String[]{"\"balance\":0", "\"balance\":100", "\"balance\":-1",
            "\"openingBalance\":100", "\"id\":\"" + UUID.randomUUID() + "\"",
            "\"createdAt\":\"2020-01-01T00:00:00Z\"", "\"holderName\":\"PRIVATE_HOLDER\"",
            "\"email\":\"private@example.invalid\""}) {
            var response = post("{\"accountNumber\":\"" + number() + "\",\"currency\":\"USD\"," + field + "}");
            assertEquals(400, response.statusCode(), response.body());
            assertEquals("INVALID_REQUEST", mapper.readTree(response.body()).get("code").asString());
            assertFalse(response.body().contains("PRIVATE_HOLDER"));
        }
        assertEquals(before, countAccounts());
    }

    @Test void malformedMissingAndWrongShapeBodiesAreRejectedSafely() throws Exception {
        long before = countAccounts();
        for (String body : new String[]{"", "{", "null", "[]", "\"not-an-object\"", "{\"accountNumber\":{}}"}) {
            var response = post(body);
            assertEquals(400, response.statusCode(), response.body());
            assertEquals("INVALID_REQUEST", mapper.readTree(response.body()).get("code").asString());
            assertFalse(response.body().contains("Exception"));
        }
        assertEquals(before, countAccounts());
    }

    @Test void duplicateAccountNumberReturnsSafeConflict() throws Exception {
        String number = number();
        var first = post(body(number));
        assertEquals(201, first.statusCode(), first.body());
        var duplicate = post(body(number));
        assertEquals(409, duplicate.statusCode(), duplicate.body());
        assertEquals("ACCOUNT_CONFLICT", mapper.readTree(duplicate.body()).get("code").asString());
        assertFalse(duplicate.body().contains(number)); assertFalse(duplicate.body().contains("INSERT"));
        assertEquals(1, countNumber(number));
        assertStoredZeroAccount(mapper.readTree(first.body()), number);
    }

    @Test void concurrentDuplicateNumbersCreateOneAccount() throws Exception {
        String number = number();
        var first = http.sendAsync(request(body(number)), HttpResponse.BodyHandlers.ofString());
        var second = http.sendAsync(request(body(number)), HttpResponse.BodyHandlers.ofString());
        var a = first.get(20, TimeUnit.SECONDS); var b = second.get(20, TimeUnit.SECONDS);
        assertTrue((a.statusCode()==201 && b.statusCode()==409) || (a.statusCode()==409 && b.statusCode()==201),
            a.statusCode() + ": " + a.body() + "; " + b.statusCode() + ": " + b.body());
        assertEquals(1, countNumber(number));
        assertStoredZeroAccount(mapper.readTree(a.statusCode()==201 ? a.body() : b.body()), number);
    }

    private void databaseFailure(boolean deferred) throws Exception {
        String number = number(), suffix = UUID.randomUUID().toString().replace("-", "");
        String function = "api_failure_" + suffix, trigger = "api_failure_" + suffix;
        try (var c = dataSource.getConnection(); var s = c.createStatement()) {
            s.execute("CREATE FUNCTION " + function + "() RETURNS TRIGGER LANGUAGE plpgsql AS $$ BEGIN "
                + "IF NEW.account_number='" + number + "' THEN RAISE EXCEPTION 'PRIVATE_DATABASE_FAILURE' USING ERRCODE='23514'; END IF; RETURN NEW; END $$");
            try {
                s.execute((deferred ? "CREATE CONSTRAINT TRIGGER " + trigger + " AFTER INSERT ON accounts DEFERRABLE INITIALLY DEFERRED"
                    : "CREATE TRIGGER " + trigger + " BEFORE INSERT ON accounts")
                    + " FOR EACH ROW EXECUTE FUNCTION " + function + "()");
                var response = post(body(number));
                assertTrue(response.statusCode()==500 || response.statusCode()==503, response.statusCode() + ": " + response.body());
                var error = mapper.readTree(response.body());
                assertTrue(error.get("code").asString().equals("ACCOUNT_CREATION_FAILED") || error.get("code").asString().equals("DATABASE_UNAVAILABLE"));
                assertFalse(response.body().contains("PRIVATE_DATABASE_FAILURE"));
                assertFalse(response.body().contains("SQLException")); assertFalse(response.body().contains(number));
                assertEquals(0, countNumber(number));
            } finally {
                s.execute("DROP TRIGGER IF EXISTS " + trigger + " ON accounts");
                s.execute("DROP FUNCTION " + function + "()");
            }
        }
    }

    @Test void databaseConstraintFailureIsSafeAndRollsBackAccount() throws Exception { databaseFailure(false); }
    @Test void deferredCommitFailureCannotReturnCreatedOrPersistAccount() throws Exception { databaseFailure(true); }
}
