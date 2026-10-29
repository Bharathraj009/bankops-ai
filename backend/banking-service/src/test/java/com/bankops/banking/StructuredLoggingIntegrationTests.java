package com.bankops.banking;

import java.net.URI;
import java.net.http.*;
import java.time.Duration;
import java.util.*;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import static org.junit.jupiter.api.Assertions.*;

@ExtendWith(OutputCaptureExtension.class)
@SpringBootTest(webEnvironment=SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties={"logging.level.root=OFF", "server.tomcat.threads.max=1", "server.tomcat.threads.min-spare=1"})
class StructuredLoggingIntegrationTests extends IsolatedPostgresTest {
    @Value("${local.server.port}") int port;
    @Autowired DataSource dataSource;
    private final HttpClient http=HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build();
    private HttpResponse<String> send(String path,String id,String body,String key) throws Exception {
        var request=operatorRequest(URI.create("http://localhost:"+port+path)).timeout(Duration.ofSeconds(10));
        if(id!=null) request.header("X-Correlation-ID",id);
        if(body!=null) request.header("Content-Type","application/json").header("Idempotency-Key",key)
            .POST(HttpRequest.BodyPublishers.ofString(body));
        return http.send(request.build(),HttpResponse.BodyHandlers.ofString());
    }
    private List<tools.jackson.databind.JsonNode> events(CapturedOutput output,String id) throws Exception {
        // afterCompletion and the filter finish just after the HTTP client can receive its response.
        for(int i=0;i<100 && !output.getAll().contains("\"correlation_id\":\""+id+"\"");i++) Thread.sleep(10);
        var mapper=new tools.jackson.databind.ObjectMapper();
        List<tools.jackson.databind.JsonNode> result=new ArrayList<>();
        for(String line:output.getAll().split("\\R")) {
            if(line.startsWith("{") && line.contains(id)) result.add(mapper.readTree(line));
        }
        assertFalse(result.isEmpty(),"Expected correlated JSON event");
        for(var event:result) {
            assertEquals(id,event.get("correlation_id").asString());
            assertNotNull(event.get("@timestamp"));
            assertEquals("INFO",event.path("log").path("level").asString());
            assertEquals("banking-service",event.path("service").path("name").asString());
            assertFalse(event.path("log").path("logger").asString().isEmpty()); assertNotNull(event.get("message"));
        }
        return result;
    }
    @Test void appenderRejectsFrameworkDiagnosticsAndArbitraryStructuredFields(CapturedOutput output) {
        var logger=(ch.qos.logback.classic.Logger) org.slf4j.LoggerFactory.getLogger("org.springframework.web.privacy-test");
        var previous=logger.getLevel();
        try {
            logger.setLevel(ch.qos.logback.classic.Level.DEBUG);
            logger.error("PRIVATE_SQL_PASSWORD request body balance account number",new IllegalStateException("PRIVATE_EXCEPTION"));
            org.slf4j.LoggerFactory.getLogger(com.bankops.banking.observability.SafeEventLogger.class).atInfo()
                .addKeyValue("credentials","PRIVATE_STRUCTURED_CREDENTIAL").log("HTTP request completed");
            org.slf4j.MDC.put("credentials","PRIVATE_MDC_CREDENTIAL");
            new com.bankops.banking.observability.SafeEventLogger().requestCompleted(200);
        } finally {
            logger.setLevel(previous);org.slf4j.MDC.remove("credentials");
        }
        for(String secret:List.of("PRIVATE_SQL_PASSWORD","PRIVATE_EXCEPTION","PRIVATE_STRUCTURED_CREDENTIAL","PRIVATE_MDC_CREDENTIAL")) {
            assertFalse(output.getAll().contains(secret));
        }
    }
    @Test void generatesPropagatesAndRejectsUnsafeCorrelationIdsWithoutThreadLeakage(CapturedOutput output) throws Exception {
        String propagated=UUID.randomUUID().toString();
        var first=send("/actuator/health",propagated,null,null);
        assertEquals(200,first.statusCode()); assertEquals(propagated,first.headers().firstValue("X-Correlation-ID").orElseThrow());
        events(output,propagated);
        for(String supplied:Arrays.asList(null,"PERSONAL_INFORMATION@example.com","x".repeat(200))) {
            var response=send("/api/v1/accounts/not-a-uuid",supplied,null,null);
            assertEquals(400,response.statusCode());
            String id=response.headers().firstValue("X-Correlation-ID").orElseThrow();
            assertEquals(id,UUID.fromString(id).toString()); assertNotEquals(propagated,id);
            assertNotEquals(supplied,id); events(output,id);
        }
        var duplicate=operatorRequest(URI.create("http://localhost:"+port+"/actuator/health"))
            .header("X-Correlation-ID",propagated).header("X-Correlation-ID",UUID.randomUUID().toString()).build();
        var response=http.send(duplicate,HttpResponse.BodyHandlers.ofString());
        assertEquals(200,response.statusCode()); assertNotEquals(propagated,response.headers().firstValue("X-Correlation-ID").orElseThrow());
        assertFalse(output.getAll().contains("PERSONAL_INFORMATION"));
    }
    @Test void logsBoundedOutcomesWithoutFinancialOrRequestDetails(CapturedOutput output) throws Exception {
        UUID source=UUID.randomUUID(),destination=UUID.randomUUID();
        String key="PRIVATE_KEY_"+UUID.randomUUID(),number="PRIVATE_ACCOUNT_"+UUID.randomUUID();
        try(var c=dataSource.getConnection(); var s=c.prepareStatement("INSERT INTO accounts(id,account_number,balance) VALUES (?,?,100),(?,?,0)")) {
            s.setObject(1,source);s.setString(2,number);s.setObject(3,destination);s.setString(4,number+"_DEST");s.executeUpdate();
        }
        String body="{\"sourceAccountId\":\""+source+"\",\"destinationAccountId\":\""+destination+"\",\"amount\":10}";
        String[] outcomes={"completed","replayed","idempotency_conflict","rejected","invalid_request"};
        int[] statuses={201,200,409,422,400};
        String transferId=null;
        for(int i=0;i<outcomes.length;i++) {
            String id=UUID.randomUUID().toString();
            String requestBody=i==2?body.replace(":10}",":11}"):i==3?body.replace(":10}",":1000}"):i==4?"{\"password\":\"PRIVATE_CREDENTIAL\",\"personal\":\"PRIVATE_PERSON\"}":body;
            var response=send("/api/v1/transfers",id,requestBody,i==3?key+"_FUNDS":key);
            assertEquals(statuses[i],response.statusCode());
            assertEquals(id,response.headers().firstValue("X-Correlation-ID").orElseThrow());
            if(i==0) transferId=new tools.jackson.databind.ObjectMapper().readTree(response.body()).get("id").asString();
            var logged=events(output,id);
            final String expected=outcomes[i];
            assertTrue(logged.stream().anyMatch(e -> "transfer_outcome".equals(e.path("event_type").asString())
                && expected.equals(e.path("outcome").asString())));
        }
        for(String secret:List.of(source.toString(),destination.toString(),transferId,key,number,"PRIVATE_CREDENTIAL","PRIVATE_PERSON","sourceAccountId","destinationAccountId","balance")) {
            assertFalse(output.getAll().contains(secret),"Sensitive value appeared in log");
        }
    }
}
