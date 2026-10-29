package com.bankops.banking;

import com.bankops.banking.observability.SafeTracing;
import io.opentelemetry.context.Context;
import io.opentelemetry.sdk.trace.*;
import java.net.URI;
import java.net.http.*;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicInteger;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.*;
import org.springframework.boot.test.context.*;
import org.springframework.context.annotation.*;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

@SpringBootTest(webEnvironment=SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties={"spring.datasource.hikari.maximum-pool-size=2","spring.datasource.hikari.minimum-idle=1"})
@org.springframework.test.annotation.DirtiesContext(classMode=org.springframework.test.annotation.DirtiesContext.ClassMode.AFTER_CLASS)
@Import(TracingFailureIntegrationTests.Failures.class)
class TracingFailureIntegrationTests extends IsolatedPostgresTest {
    static class BrokenProcessor implements SpanProcessor {
        final AtomicInteger starts=new AtomicInteger(),ends=new AtomicInteger();
        @Override public void onStart(Context parent,ReadWriteSpan span) {starts.incrementAndGet();throw new IllegalStateException("PRIVATE_START_FAILURE");}
        @Override public boolean isStartRequired() {return true;}
        @Override public void onEnd(ReadableSpan span) {ends.incrementAndGet();throw new IllegalStateException("PRIVATE_EXPORT_FAILURE");}
        @Override public boolean isEndRequired() {return true;}
    }
    @TestConfiguration(proxyBeanMethods=false) static class Failures {
        @Bean BrokenProcessor brokenProcessor() {return new BrokenProcessor();}
    }
    @Value("${local.server.port}") int port;
    @Autowired DataSource dataSource;
    @Autowired BrokenProcessor broken;
    @MockitoSpyBean SafeTracing tracing;
    @Test void startAndExportFailuresCannotChangeCommitRetryOrRollback() throws Exception {
        int starts=broken.starts.get(),ends=broken.ends.get();verifyMoney();
        assertTrue(broken.starts.get()>starts);assertTrue(broken.ends.get()>ends);
    }
    @Test void tracingSetupFailureCannotExecuteBusinessWorkTwice() throws Exception {
        doThrow(new IllegalStateException("Tracing unavailable")).when(tracing).open(anyString(),any(),any());
        verifyMoney();verify(tracing,atLeastOnce()).open(anyString(),any(),any());
    }
    private void verifyMoney() throws Exception {
        UUID source=UUID.randomUUID(),destination=UUID.randomUUID();
        try(var c=dataSource.getConnection();var s=c.prepareStatement("INSERT INTO accounts(id,account_number,balance) VALUES (?,?,100),(?,?,0)")) {
            s.setObject(1,source);s.setString(2,source.toString());s.setObject(3,destination);s.setString(4,destination.toString());s.executeUpdate();
        }
        try(var http=HttpClient.newHttpClient()) {
            String key=UUID.randomUUID().toString();
            String body="{\"sourceAccountId\":\""+source+"\",\"destinationAccountId\":\""+destination+"\",\"amount\":10}";
            var request=operatorRequest(URI.create("http://localhost:"+port+"/api/v1/transfers"))
                .header("Content-Type","application/json").header("Idempotency-Key",key).POST(HttpRequest.BodyPublishers.ofString(body)).build();
            var first=http.send(request,HttpResponse.BodyHandlers.ofString());assertEquals(201,first.statusCode());
            var retry=http.send(request,HttpResponse.BodyHandlers.ofString());assertEquals(200,retry.statusCode());assertEquals(first.body(),retry.body());
            assertTrue(first.headers().firstValue("X-Correlation-ID").isPresent());
            var insufficient=operatorRequest(request.uri()).header("Content-Type","application/json")
                .header("Idempotency-Key",key+"_FUNDS").POST(HttpRequest.BodyPublishers.ofString(body.replace(":10}",":1000}"))).build();
            assertEquals(422,http.send(insufficient,HttpResponse.BodyHandlers.ofString()).statusCode());
        }
        try(var c=dataSource.getConnection();var s=c.prepareStatement("""
            SELECT (SELECT balance FROM accounts WHERE id=?),(SELECT balance FROM accounts WHERE id=?),
                (SELECT count(*) FROM transfers WHERE source_account_id=?),
                (SELECT count(*) FROM ledger_entries WHERE account_id IN (?,?))
            """)) {
            s.setObject(1,source);s.setObject(2,destination);s.setObject(3,source);s.setObject(4,source);s.setObject(5,destination);
            try(var r=s.executeQuery()) {assertTrue(r.next());assertEquals(new java.math.BigDecimal("90.00"),r.getBigDecimal(1));
                assertEquals(new java.math.BigDecimal("10.00"),r.getBigDecimal(2));assertEquals(1,r.getInt(3));assertEquals(2,r.getInt(4));}
        }
    }
}
