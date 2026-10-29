package com.bankops.banking;

import com.bankops.banking.dev.DevFundingController;
import com.bankops.banking.dev.DevFundingService;
import com.bankops.banking.dev.DevReserveBootstrap;
import com.bankops.banking.dev.DevReserveBootstrapRunner;
import java.net.URI;
import java.net.http.*;
import java.sql.DriverManager;
import java.time.Duration;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.boot.builder.SpringApplicationBuilder;
import static org.junit.jupiter.api.Assertions.*;

class DevFundingProfileIntegrationTests {
    @Test void routeIsAbsentWithoutDevAndWhenProductionOrTestIsAlsoActive() throws Exception {
        String url=System.getenv("BANKOPS_TEST_DB_URL"),user=System.getenv("BANKOPS_TEST_DB_USER"),password=System.getenv("BANKOPS_TEST_DB_PASSWORD");
        assertNotNull(url,"Explicit isolated PostgreSQL is required"); assertNotNull(user); assertNotNull(password);
        try(var http=HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build()) {
            for(String profiles:new String[]{"default","prod","production","test","dev,prod","dev,production","dev,test"}) {
                String schema="profile_"+UUID.randomUUID().toString().replace("-","");
                try(var c=DriverManager.getConnection(url,user,password); var s=c.createStatement()) { s.execute("CREATE SCHEMA "+schema); }
                try {
                    try(var context=new SpringApplicationBuilder(BankingServiceApplication.class).run(
                        "--spring.profiles.active="+profiles,"--server.port=0","--spring.datasource.url="+url,
                        "--spring.datasource.username="+user,"--spring.datasource.password="+password,
                        "--spring.datasource.hikari.schema="+schema,"--spring.flyway.default-schema="+schema,
                        "--spring.flyway.schemas="+schema,"--spring.flyway.enabled=true",
                        "--spring.datasource.hikari.maximum-pool-size=2","--spring.datasource.hikari.minimum-idle=1",
                        "--logging.level.root=ERROR","--spring.main.banner-mode=off","--spring.jmx.enabled=false",
                        "--BANKOPS_BANKING_API_TOKEN=isolated-security-profile-check-only",
                        "--bankops.customer.enabled=true",
                        "--bankops.database.verify-runtime=false",
                        "--bankops.dev.reserve-bootstrap.enabled=true","--bankops.dev.funding-account-id="+UUID.randomUUID())) {
                        assertTrue(context.getBeansOfType(DevFundingController.class).isEmpty(),profiles);
                        assertTrue(context.getBeansOfType(DevFundingService.class).isEmpty(),profiles);
                        assertTrue(context.getBeansOfType(DevReserveBootstrap.class).isEmpty(),profiles);
                        assertTrue(context.getBeansOfType(DevReserveBootstrapRunner.class).isEmpty(),profiles);
                        try(var c=DriverManager.getConnection(url,user,password); var s=c.createStatement(); var r=s.executeQuery("SELECT count(*) FROM "+schema+".accounts")) {
                            assertTrue(r.next()); assertEquals(0,r.getLong(1),profiles);
                        }
                        String port=context.getEnvironment().getProperty("local.server.port");
                        var response=http.send(HttpRequest.newBuilder(URI.create("http://localhost:"+port+"/api/v1/dev/accounts/"+UUID.randomUUID()+"/fund"))
                            .timeout(Duration.ofSeconds(10)).header("Content-Type","application/json").header("Idempotency-Key","profile-probe")
                            .header("Authorization","Bearer isolated-security-profile-check-only")
                            .POST(HttpRequest.BodyPublishers.ofString("{\"amount\":1}")).build(),HttpResponse.BodyHandlers.ofString());
                        assertEquals(404,response.statusCode(),profiles+": "+response.body());
                        if(profiles.contains("prod")) {
                            var customer=http.send(HttpRequest.newBuilder(URI.create("http://localhost:"+port+"/api/v1/customer/register"))
                                .header("Content-Type","application/json").POST(HttpRequest.BodyPublishers.ofString("{}" )).build(),HttpResponse.BodyHandlers.ofString());
                            assertEquals(503,customer.statusCode(),"Portfolio customer login must stay unavailable in production");
                        }
                    }
                } finally {
                    try(var c=DriverManager.getConnection(url,user,password); var s=c.createStatement()) { s.execute("DROP SCHEMA "+schema+" CASCADE"); }
                }
            }
        }
    }
}
