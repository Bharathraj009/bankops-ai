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
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

@SpringBootTest(webEnvironment=SpringBootTest.WebEnvironment.RANDOM_PORT)
class MonitoringFailureIntegrationTests extends IsolatedPostgresTest {
    @Value("${local.server.port}") int port;
    @Autowired DataSource dataSource;
    @MockitoSpyBean MeterRegistry registry;
    @Test void failingOutcomeRegistryCannotChangeTransferResponseOrCommittedMoney() throws Exception {
        UUID source=UUID.randomUUID(),destination=UUID.randomUUID();
        try(var c=dataSource.getConnection(); var s=c.prepareStatement("INSERT INTO accounts(id,account_number,balance) VALUES (?,?,100),(?,?,0)")) {
            s.setObject(1,source); s.setString(2,source.toString()); s.setObject(3,destination); s.setString(4,destination.toString()); s.executeUpdate();
        }
        doThrow(new IllegalStateException("Monitoring unavailable")).when(registry).counter(eq("bankops.transfer.outcomes"),any(String[].class));
        try(var http=HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build()) {
            String key=UUID.randomUUID().toString();
            var request=operatorRequest(URI.create("http://localhost:"+port+"/api/v1/transfers"))
                .timeout(Duration.ofSeconds(10)).header("Content-Type","application/json").header("Idempotency-Key",key)
                .POST(HttpRequest.BodyPublishers.ofString("{\"sourceAccountId\":\""+source+"\",\"destinationAccountId\":\""+destination+"\",\"amount\":10}")).build();
            var first=http.send(request,HttpResponse.BodyHandlers.ofString()); assertEquals(201,first.statusCode(),first.body());
            var retry=http.send(request,HttpResponse.BodyHandlers.ofString()); assertEquals(200,retry.statusCode(),retry.body());
            assertEquals(first.body(),retry.body());
        }
        verify(registry,timeout(2000).atLeast(2)).counter(eq("bankops.transfer.outcomes"),any(String[].class));
        try(var c=dataSource.getConnection(); var s=c.prepareStatement("""
            SELECT (SELECT balance FROM accounts WHERE id=?),(SELECT balance FROM accounts WHERE id=?),
                (SELECT count(*) FROM transfers WHERE source_account_id=?),
                (SELECT count(*) FROM ledger_entries WHERE account_id IN (?,?))
            """)) {
            s.setObject(1,source); s.setObject(2,destination); s.setObject(3,source); s.setObject(4,source); s.setObject(5,destination);
            try(var r=s.executeQuery()) { assertTrue(r.next()); assertEquals(new java.math.BigDecimal("90.00"),r.getBigDecimal(1));
                assertEquals(new java.math.BigDecimal("10.00"),r.getBigDecimal(2)); assertEquals(1,r.getInt(3)); assertEquals(2,r.getInt(4)); }
        }
    }
}
