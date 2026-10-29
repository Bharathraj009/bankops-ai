package com.bankops.banking;

import java.net.URI;
import java.net.http.*;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(webEnvironment=SpringBootTest.WebEnvironment.RANDOM_PORT)
class ApiSecurityIntegrationTests extends IsolatedPostgresTest {
    @LocalServerPort int port;
    @Test void financialHttpRoutesRequireCredentialBeforeValidationOrDatabaseAccess() throws Exception {
        try(var http=HttpClient.newHttpClient()) {
            String base="http://localhost:"+port;
            var blocked=http.send(HttpRequest.newBuilder(URI.create(base+"/api/v1/transfers"))
                .header("Content-Type","application/json").POST(HttpRequest.BodyPublishers.ofString("{}")).build(),HttpResponse.BodyHandlers.ofString());
            assertEquals(401,blocked.statusCode());
            assertEquals(503,http.send(HttpRequest.newBuilder(URI.create(base+"/api/v1/customer/accounts")).GET().build(),HttpResponse.BodyHandlers.ofString()).statusCode());
            assertFalse(blocked.body().contains("SQL"));
            var authorized=http.send(HttpRequest.newBuilder(URI.create(base+"/api/v1/accounts/"+UUID.randomUUID()))
                .header("Authorization","Bearer "+OPERATOR_TOKEN).GET().build(),HttpResponse.BodyHandlers.ofString());
            assertEquals(404,authorized.statusCode());
            var crossSite=http.send(HttpRequest.newBuilder(URI.create(base+"/api/v1/accounts"))
                .header("Origin","https://attacker.invalid").header("Content-Type","application/json")
                .header("Authorization","Bearer "+OPERATOR_TOKEN)
                .POST(HttpRequest.BodyPublishers.ofString("{}")).build(),HttpResponse.BodyHandlers.ofString());
            assertEquals(403,crossSite.statusCode());
            assertEquals("no-store",crossSite.headers().firstValue("Cache-Control").orElseThrow());
        }
    }
}
