package com.bankops.banking;

import com.sun.net.httpserver.HttpServer;
import io.opentelemetry.sdk.OpenTelemetrySdk;
import java.net.*;
import java.net.http.*;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import javax.sql.DataSource;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.*;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.*;
import org.springframework.test.annotation.DirtiesContext;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(webEnvironment=SpringBootTest.WebEnvironment.RANDOM_PORT,properties={
    "bankops.tracing.otlp.enabled=true","spring.datasource.hikari.maximum-pool-size=2","spring.datasource.hikari.minimum-idle=1"})
@DirtiesContext(classMode=DirtiesContext.ClassMode.AFTER_CLASS)
class OtlpExportIntegrationTests extends IsolatedPostgresTest {
    private static final AtomicInteger exports=new AtomicInteger();
    private static final HttpServer receiver=createReceiver();
    private static HttpServer createReceiver() {
        try {
            var server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
            server.createContext("/v1/traces",exchange -> {
                if(exchange.getRequestBody().readAllBytes().length>0) exports.incrementAndGet();
                exchange.sendResponseHeaders(400,-1);exchange.close();
            });
            server.start();return server;
        } catch(java.io.IOException failure) {throw new ExceptionInInitializerError(failure);}
    }
    @DynamicPropertySource static void endpoint(DynamicPropertyRegistry registry) {
        registry.add("bankops.tracing.otlp.endpoint",() -> "http://127.0.0.1:"+receiver.getAddress().getPort()+"/v1/traces");
    }
    @AfterAll static void stopReceiver() {receiver.stop(0);}
    @Value("${local.server.port}") int port;
    @Autowired DataSource dataSource;
    @Autowired OpenTelemetrySdk telemetry;
    @Test void rejectedOtlpExportsCannotChangeCommittedTransferOrRetry() throws Exception {
        UUID source=UUID.randomUUID(),destination=UUID.randomUUID();
        try(var c=dataSource.getConnection();var s=c.prepareStatement("INSERT INTO accounts(id,account_number,balance) VALUES (?,?,100),(?,?,0)")) {
            s.setObject(1,source);s.setString(2,source.toString());s.setObject(3,destination);s.setString(4,destination.toString());s.executeUpdate();
        }
        try(var http=HttpClient.newHttpClient()) {
            var request=operatorRequest(URI.create("http://localhost:"+port+"/api/v1/transfers"))
                .header("Content-Type","application/json").header("Idempotency-Key",UUID.randomUUID().toString())
                .POST(HttpRequest.BodyPublishers.ofString("{\"sourceAccountId\":\""+source+"\",\"destinationAccountId\":\""+destination+"\",\"amount\":10}")).build();
            var first=http.send(request,HttpResponse.BodyHandlers.ofString());assertEquals(201,first.statusCode());
            telemetry.getSdkTracerProvider().forceFlush().join(5,TimeUnit.SECONDS);
            assertTrue(exports.get()>0,"The failing OTLP receiver must receive actual exported spans");
            var retry=http.send(request,HttpResponse.BodyHandlers.ofString());assertEquals(200,retry.statusCode());assertEquals(first.body(),retry.body());
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
