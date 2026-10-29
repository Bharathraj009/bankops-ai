package com.bankops.banking;

import io.micrometer.core.instrument.MeterRegistry;
import java.net.URI;
import java.net.http.*;
import java.time.Duration;
import java.util.UUID;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(webEnvironment=SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties="management.prometheus.metrics.export.enabled=true")
class PrometheusIntegrationTests extends IsolatedPostgresTest {
    @Value("${local.server.port}") int port;
    @Autowired MeterRegistry registry;
    @Autowired DataSource dataSource;
    private final HttpClient http=HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build();
    private HttpResponse<String> get(String path) throws Exception {
        return http.send(operatorRequest(URI.create("http://localhost:"+port+path)).timeout(Duration.ofSeconds(10)).GET().build(),HttpResponse.BodyHandlers.ofString());
    }
    private UUID account(int balance) throws Exception {
        UUID id=UUID.randomUUID();
        try(var c=dataSource.getConnection(); var s=c.prepareStatement("INSERT INTO accounts(id,account_number,balance) VALUES (?,?,?)")) {
            s.setObject(1,id); s.setString(2,"PRIVATE_CUSTOMER_"+id); s.setInt(3,balance); s.executeUpdate();
        }
        return id;
    }
    private HttpResponse<String> post(String key,UUID source,UUID destination,int amount) throws Exception {
        return http.send(operatorRequest(URI.create("http://localhost:"+port+"/api/v1/transfers"))
            .timeout(Duration.ofSeconds(10)).header("Content-Type","application/json").header("Idempotency-Key",key)
            .POST(HttpRequest.BodyPublishers.ofString("{\"sourceAccountId\":\""+source+"\",\"destinationAccountId\":\""+destination+"\",\"amount\":"+amount+"}")).build(),HttpResponse.BodyHandlers.ofString());
    }
    private double outcome(String value) {
        return registry.counter("bankops.transfer.outcomes","operation","transfer","outcome",value).count();
    }
    @Test void healthAndPrometheusAreExposedWithoutOtherActuatorEndpoints() throws Exception {
        var health=get("/actuator/health"); assertEquals(200,health.statusCode());
        assertTrue(health.body().contains("UP")); assertFalse(health.body().contains("jdbc")); assertFalse(health.body().contains("components"));
        var scrape=get("/actuator/prometheus"); assertEquals(200,scrape.statusCode(),scrape.body());
        assertTrue(scrape.body().contains("jvm_memory_used_bytes"));
        assertEquals(404,get("/actuator/env").statusCode()); assertEquals(404,get("/actuator/metrics").statusCode());
    }
    @Test void countsOutcomesAndHttpErrorsWithLatencyAndNoSensitiveLabels() throws Exception {
        UUID source=account(100),destination=account(0); String key="PRIVATE_KEY_"+UUID.randomUUID();
        double completed=outcome("completed"),replayed=outcome("replayed"),conflict=outcome("idempotency_conflict"),rejected=outcome("rejected");
        var first=post(key,source,destination,10); assertEquals(201,first.statusCode(),first.body());
        assertEquals(200,post(key,source,destination,10).statusCode());
        assertEquals(409,post(key,source,destination,11).statusCode());
        assertEquals(422,post(UUID.randomUUID().toString(),source,destination,1000).statusCode());
        assertEquals(200,get("/api/v1/accounts/"+source).statusCode());
        assertEquals(404,get("/api/v1/accounts/"+UUID.randomUUID()).statusCode());
        assertEquals(404,get("/PRIVATE_PATH_"+source).statusCode());
        assertEquals(completed+1,outcome("completed")); assertEquals(replayed+1,outcome("replayed"));
        assertEquals(conflict+1,outcome("idempotency_conflict")); assertEquals(rejected+1,outcome("rejected"));
        var scrape=get("/actuator/prometheus"); assertEquals(200,scrape.statusCode()); String metrics=scrape.body();
        assertTrue(metrics.contains("bankops_transfer_outcomes_total"));
        assertTrue(metrics.contains("http_server_requests_seconds_count")); assertTrue(metrics.contains("http_server_requests_seconds_sum"));
        assertTrue(metrics.contains("http_server_requests_seconds_bucket")); assertTrue(metrics.contains("status=\"409\""));
        assertTrue(metrics.contains("status=\"422\"")); assertTrue(metrics.contains("uri=\"/api/v1/accounts/{accountId}\""));
        assertFalse(metrics.contains(source.toString())); assertFalse(metrics.contains(destination.toString()));
        assertFalse(metrics.contains(key)); assertFalse(metrics.contains("PRIVATE_CUSTOMER")); assertFalse(metrics.contains("PRIVATE_PATH"));
        var json=new tools.jackson.databind.ObjectMapper().readTree(first.body());
        assertFalse(metrics.contains(json.get("id").asString()));
    }
}
