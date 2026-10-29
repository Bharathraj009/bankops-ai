package com.bankops.banking;

import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.sdk.testing.exporter.InMemorySpanExporter;
import io.opentelemetry.sdk.trace.SpanProcessor;
import io.opentelemetry.sdk.trace.data.SpanData;
import io.opentelemetry.sdk.trace.export.SimpleSpanProcessor;
import java.net.URI;
import java.net.http.*;
import java.time.Duration;
import java.util.*;
import javax.sql.DataSource;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.*;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.test.system.*;
import org.springframework.context.annotation.*;
import static org.junit.jupiter.api.Assertions.*;

@ExtendWith(OutputCaptureExtension.class)
@SpringBootTest(webEnvironment=SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties={"spring.datasource.hikari.maximum-pool-size=2","spring.datasource.hikari.minimum-idle=1"})
@org.springframework.test.annotation.DirtiesContext(classMode=org.springframework.test.annotation.DirtiesContext.ClassMode.AFTER_CLASS)
@Import(TracingIntegrationTests.Capture.class)
class TracingIntegrationTests extends IsolatedPostgresTest {
    @TestConfiguration(proxyBeanMethods=false)
    static class Capture {
        @Bean InMemorySpanExporter exporter() {return InMemorySpanExporter.create();}
        @Bean SpanProcessor captureProcessor(InMemorySpanExporter exporter) {return SimpleSpanProcessor.create(exporter);}
    }
    @Value("${local.server.port}") int port;
    @Autowired InMemorySpanExporter exporter;
    @Autowired DataSource dataSource;
    private final HttpClient http=HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build();
    @BeforeEach void reset() {exporter.reset();}
    private HttpRequest.Builder request(String path) {return operatorRequest(URI.create("http://localhost:"+port+path)).timeout(Duration.ofSeconds(10));}
    private List<SpanData> finished(int servers) throws Exception {
        for(int i=0;i<200;i++) {
            var spans=exporter.getFinishedSpanItems();
            if(spans.stream().filter(s -> s.getKind()==SpanKind.SERVER).count()>=servers) return spans;
            Thread.sleep(10);
        }
        fail("Timed out waiting for server spans");return List.of();
    }
    private String traceId() {return UUID.randomUUID().toString().replace("-","");}
    private void safe(List<SpanData> spans,String... secrets) {
        for(var span:spans) {
            assertTrue(Set.of("http.request","transfer.create","transfer.read","transfer.fund","db.call").contains(span.getName()));
            assertTrue(span.getEvents().isEmpty());assertTrue(span.getLinks().isEmpty());
            assertEquals("",span.getStatus().getDescription());
            span.getAttributes().forEach((key,value) -> assertTrue(Set.of("db.system.name","http.response.status_code").contains(key.getKey())));
            span.getResource().getAttributes().forEach((key,value) -> assertEquals("service.name",key.getKey()));
            assertTrue(span.getSpanContext().getTraceState().isEmpty());
            String serialized=span.toString();
            for(String secret:secrets) assertFalse(serialized.contains(secret),"Sensitive data in span");
        }
    }
    @Test void transferDatabaseAndLogsShareW3cTraceWithoutSensitiveDetails(CapturedOutput output) throws Exception {
        UUID source=UUID.randomUUID(),destination=UUID.randomUUID();
        String accountNumber="PRIVATE_ACCOUNT_"+UUID.randomUUID(),key="PRIVATE_KEY_"+UUID.randomUUID();
        try(var c=dataSource.getConnection();var s=c.prepareStatement("INSERT INTO accounts(id,account_number,balance) VALUES (?,?,100),(?,?,0)")) {
            s.setObject(1,source);s.setString(2,accountNumber);s.setObject(3,destination);s.setString(4,accountNumber+"_DEST");s.executeUpdate();
        }
        String trace=traceId(),parent=traceId().substring(0,16),correlation=UUID.randomUUID().toString();
        String body="{\"sourceAccountId\":\""+source+"\",\"destinationAccountId\":\""+destination+"\",\"amount\":10}";
        var response=http.send(request("/api/v1/transfers").header("traceparent","00-"+trace+"-"+parent+"-01")
            .header("tracestate","private=PRIVATE_VENDOR_STATE").header("baggage","customer=PRIVATE_PERSON")
            .setHeader("Authorization","Bearer "+OPERATOR_TOKEN).header("X-Private-Credential","PRIVATE_CREDENTIAL").header("X-Correlation-ID",correlation)
            .header("Idempotency-Key",key).header("Content-Type","application/json")
            .POST(HttpRequest.BodyPublishers.ofString(body)).build(),HttpResponse.BodyHandlers.ofString());
        assertEquals(201,response.statusCode());assertEquals(correlation,response.headers().firstValue("X-Correlation-ID").orElseThrow());
        var spans=finished(1);
        var server=spans.stream().filter(s -> s.getKind()==SpanKind.SERVER).findFirst().orElseThrow();
        assertEquals(trace,server.getTraceId());assertEquals(parent,server.getParentSpanId());assertTrue(server.getParentSpanContext().isRemote());
        assertEquals("00-"+trace+"-"+server.getSpanId()+"-01",response.headers().firstValue("traceparent").orElseThrow());
        var operation=spans.stream().filter(s -> "transfer.create".equals(s.getName())).findFirst().orElseThrow();
        assertEquals(server.getSpanId(),operation.getParentSpanId());
        var db=spans.stream().filter(s -> "db.call".equals(s.getName())).toList();assertTrue(db.size()>=6);
        for(var span:db) {assertEquals(operation.getSpanId(),span.getParentSpanId());assertEquals(SpanKind.CLIENT,span.getKind());}
        for(var span:spans) assertEquals(trace,span.getTraceId());
        safe(spans,source.toString(),destination.toString(),accountNumber,key,"PRIVATE_VENDOR_STATE","PRIVATE_PERSON","PRIVATE_CREDENTIAL",OPERATOR_TOKEN,body);
        boolean logged=false;
        for(String line:output.getAll().split("\\R")) {
            if(line.startsWith("{") && line.contains(correlation)) {
                var event=new tools.jackson.databind.ObjectMapper().readTree(line);
                assertEquals(trace,event.path("trace_id").asString());assertEquals(server.getSpanId(),event.path("span_id").asString());logged=true;
            }
        }
        assertTrue(logged);
        for(String secret:List.of(source.toString(),destination.toString(),accountNumber,key,"PRIVATE_VENDOR_STATE","PRIVATE_PERSON","PRIVATE_CREDENTIAL")) assertFalse(output.getAll().contains(secret));
    }
    @Test void generatesFreshContextForMissingOrInvalidParentsAndPropagatesResponseContext() throws Exception {
        Set<String> seen=new HashSet<>();String forwarded=null,previousSpan=null;
        for(String supplied:Arrays.asList(null,"PRIVATE_INVALID_TRACEPARENT","00-"+"0".repeat(32)+"-"+"0".repeat(16)+"-01")) {
            var builder=request("/api/v1/accounts/"+UUID.randomUUID()+"?password=PRIVATE_QUERY");
            if(supplied!=null) builder.header("traceparent",supplied);
            var response=http.send(builder.build(),HttpResponse.BodyHandlers.ofString());assertEquals(404,response.statusCode());
            String header=response.headers().firstValue("traceparent").orElseThrow();
            assertTrue(header.matches("00-[0-9a-f]{32}-[0-9a-f]{16}-01"));assertTrue(seen.add(header.split("-")[1]));
            forwarded=header;previousSpan=header.split("-")[2];
        }
        var response=http.send(request("/api/v1/accounts/not-a-uuid").header("traceparent",forwarded).build(),HttpResponse.BodyHandlers.ofString());
        assertEquals(400,response.statusCode());var spans=finished(4);
        final String parent=previousSpan;
        assertTrue(spans.stream().anyMatch(s -> s.getKind()==SpanKind.SERVER && parent.equals(s.getParentSpanId())));
        safe(spans,"PRIVATE_QUERY","PRIVATE_INVALID_TRACEPARENT");
    }
    @Test void concurrentRequestsDoNotShareTraceContext() throws Exception {
        Map<String,String> parents=new HashMap<>();List<java.util.concurrent.CompletableFuture<HttpResponse<String>>> requests=new ArrayList<>();
        for(int i=0;i<8;i++) {
            String trace=traceId(),parent=traceId().substring(0,16);parents.put(trace,parent);
            requests.add(http.sendAsync(request("/api/v1/accounts/"+UUID.randomUUID()).header("traceparent","00-"+trace+"-"+parent+"-01").build(),HttpResponse.BodyHandlers.ofString()));
        }
        for(var request:requests) assertEquals(404,request.join().statusCode());
        var spans=finished(8);assertEquals(8,spans.stream().filter(s -> s.getKind()==SpanKind.SERVER).count());
        for(var span:spans) {
            assertTrue(parents.containsKey(span.getTraceId()));
            if(span.getKind()==SpanKind.SERVER) assertEquals(parents.get(span.getTraceId()),span.getParentSpanId());
        }
        safe(spans);
    }
}
