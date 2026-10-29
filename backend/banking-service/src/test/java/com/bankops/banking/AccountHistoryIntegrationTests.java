package com.bankops.banking;

import java.math.BigDecimal;
import java.net.URI;
import java.net.http.*;
import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.UUID;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class AccountHistoryIntegrationTests extends IsolatedPostgresTest {
    @Value("${local.server.port}") int port;
    @Autowired DataSource dataSource;
    @Autowired ObjectMapper mapper;
    private final HttpClient http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build();
    private UUID account() throws Exception {
        UUID id = UUID.randomUUID();
        try (var c=dataSource.getConnection(); var s=c.prepareStatement("INSERT INTO accounts(id,account_number,balance) VALUES (?,?,1000)")) {
            s.setObject(1,id); s.setString(2,id.toString()); s.executeUpdate();
        }
        return id;
    }
    private UUID transfer(UUID id, UUID source, UUID destination, String amount, String status, String postingTime) throws Exception {
        try (var c=dataSource.getConnection()) {
            c.setAutoCommit(false);
            try (var s=c.prepareStatement("INSERT INTO transfers(id,source_account_id,destination_account_id,amount,created_at) VALUES (?,?,?,?,'2020-01-01T00:00:00Z')")) {
                s.setObject(1,id); s.setObject(2,source); s.setObject(3,destination); s.setBigDecimal(4,new BigDecimal(amount)); s.executeUpdate();
            }
            if(postingTime!=null) {
                try (var s=c.prepareStatement("""
                    INSERT INTO ledger_entries(id,transfer_id,account_id,entry_type,amount,created_at)
                    VALUES (?,?,?,'DEBIT',?,?),(?,?,?,'CREDIT',?,?)
                    """)) {
                    s.setObject(1,UUID.randomUUID()); s.setObject(2,id); s.setObject(3,source);
                    s.setBigDecimal(4,new BigDecimal(amount)); s.setObject(5,OffsetDateTime.parse(postingTime));
                    s.setObject(6,UUID.randomUUID()); s.setObject(7,id); s.setObject(8,destination);
                    s.setBigDecimal(9,new BigDecimal(amount)); s.setObject(10,OffsetDateTime.parse(postingTime)); s.executeUpdate();
                }
            }
            try (var s=c.prepareStatement("UPDATE transfers SET status=? WHERE id=?")) {
                s.setString(1,status); s.setObject(2,id); s.executeUpdate();
            }
            c.commit();
        }
        return id;
    }
    private HttpResponse<String> get(String id,String query) throws Exception {
        return http.send(operatorRequest(URI.create("http://localhost:"+port+"/api/v1/accounts/"+id+"/transactions"+query))
            .timeout(Duration.ofSeconds(10)).GET().build(),HttpResponse.BodyHandlers.ofString());
    }
    private JsonNode history(UUID id,String query) throws Exception {
        var response=get(id.toString(),query); assertEquals(200,response.statusCode(),response.body());
        return mapper.readTree(response.body());
    }
    private String snapshot() throws Exception {
        try(var c=dataSource.getConnection(); var s=c.createStatement(); var r=s.executeQuery("""
            SELECT (SELECT md5(coalesce(string_agg(to_jsonb(a)::text,'' ORDER BY id),'')) FROM accounts a),
                (SELECT md5(coalesce(string_agg(to_jsonb(t)::text,'' ORDER BY id),'')) FROM transfers t),
                (SELECT md5(coalesce(string_agg(to_jsonb(l)::text,'' ORDER BY id),'')) FROM ledger_entries l),
                (SELECT md5(coalesce(string_agg(to_jsonb(i)::text,'' ORDER BY id),'')) FROM idempotency_records i)
            """)) {
            assertTrue(r.next()); return r.getString(1)+r.getString(2)+r.getString(3)+r.getString(4);
        }
    }
    private void entry(JsonNode entry,UUID id,String direction,String amount,String timestamp) {
        assertEquals(6,entry.size()); assertEquals(id.toString(),entry.get("transferId").asString());
        assertEquals(direction,entry.get("direction").asString()); assertEquals("USD",entry.get("currency").asString());
        assertEquals("COMPLETED",entry.get("status").asString());
        assertEquals(0,new BigDecimal(amount).compareTo(entry.get("amount").decimalValue()));
        assertEquals(OffsetDateTime.parse(timestamp).toInstant(),OffsetDateTime.parse(entry.get("timestamp").asString()).toInstant());
        assertFalse(entry.has("accountId")); assertFalse(entry.has("entryType")); assertFalse(entry.has("idempotencyKey"));
    }

    @Test void includesIncomingAndOutgoingCompletedLedgerPostingsOnlyWithoutWrites() throws Exception {
        UUID account=account(),other=account(),unrelated=account();
        UUID outgoing=transfer(UUID.randomUUID(),account,other,"10.25","COMPLETED","2026-01-01T00:00:00Z");
        UUID incoming=transfer(UUID.randomUUID(),other,account,"20.50","COMPLETED","2026-01-03T00:00:00Z");
        transfer(UUID.randomUUID(),account,other,"3","PENDING","2026-01-05T00:00:00Z");
        transfer(UUID.randomUUID(),account,other,"3","PENDING",null);
        transfer(UUID.randomUUID(),other,account,"3","FAILED",null);
        transfer(UUID.randomUUID(),other,unrelated,"3","COMPLETED","2026-01-06T00:00:00Z");
        String before=snapshot(); var result=history(account,"");
        assertEquals(2,result.get("totalElements").asLong()); assertEquals(1,result.get("totalPages").asLong());
        assertEquals(0,result.get("page").asInt()); assertEquals(20,result.get("size").asInt());
        assertEquals(2,result.get("transactions").size());
        entry(result.get("transactions").get(0),incoming,"INCOMING","20.50","2026-01-03T00:00:00Z");
        entry(result.get("transactions").get(1),outgoing,"OUTGOING","10.25","2026-01-01T00:00:00Z");
        assertEquals(before,snapshot());
    }
    @Test void paginatesNewestFirstWithStableTieOrderingAndEmptyBeyondLastPage() throws Exception {
        UUID account=account(),other=account();
        UUID old=transfer(UUID.randomUUID(),account,other,"1","COMPLETED","2026-01-01T00:00:00Z");
        UUID low=transfer(UUID.fromString("00000000-0000-0000-0000-000000000001"),other,account,"2","COMPLETED","2026-01-02T00:00:00Z");
        UUID high=transfer(UUID.fromString("00000000-0000-0000-0000-000000000002"),account,other,"3","COMPLETED","2026-01-02T00:00:00Z");
        var first=history(account,"?page=0&size=2"); var second=history(account,"?page=1&size=2");
        assertEquals(3,first.get("totalElements").asLong()); assertEquals(2,first.get("totalPages").asLong());
        assertEquals(high.toString(),first.get("transactions").get(0).get("transferId").asString());
        assertEquals(low.toString(),first.get("transactions").get(1).get("transferId").asString());
        assertEquals(1,second.get("transactions").size()); assertEquals(old.toString(),second.get("transactions").get(0).get("transferId").asString());
        assertEquals(first,history(account,"?page=0&size=2"));
        var beyond=history(account,"?page=2147483647&size=100");
        assertEquals(0,beyond.get("transactions").size()); assertEquals(3,beyond.get("totalElements").asLong());
    }
    @Test void defaultPaginationLimitsResultsAndAllowsMaximumSize() throws Exception {
        UUID account=account(),other=account();
        for(int i=0;i<25;i++) transfer(UUID.randomUUID(),account,other,"1","COMPLETED",
            OffsetDateTime.parse("2026-01-01T00:00:00Z").plusSeconds(i).toString());
        var result=history(account,""); assertEquals(20,result.get("transactions").size());
        assertEquals(25,result.get("totalElements").asLong()); assertEquals(2,result.get("totalPages").asLong());
        assertEquals(5,history(account,"?page=1").get("transactions").size());
        assertEquals(25,history(account,"?size=100").get("transactions").size());
    }
    @Test void existingAccountWithoutPostingsReturnsEmptyPage() throws Exception {
        var result=history(account(),""); assertEquals(0,result.get("transactions").size());
        assertEquals(0,result.get("totalElements").asLong()); assertEquals(0,result.get("totalPages").asLong());
    }
    @Test void invalidIdsAndPaginationReturnSafeErrorsAndUnknownAccountReturns404() throws Exception {
        UUID account=account(); String before=snapshot();
        var unknown=get(UUID.randomUUID().toString(),""); assertEquals(404,unknown.statusCode(),unknown.body());
        assertEquals("ACCOUNT_NOT_FOUND",mapper.readTree(unknown.body()).get("code").asString());
        var malformed=get("PRIVATE_INVALID_ID",""); assertEquals(400,malformed.statusCode(),malformed.body());
        assertEquals("INVALID_ACCOUNT_ID",mapper.readTree(malformed.body()).get("code").asString());
        assertFalse(malformed.body().contains("PRIVATE_INVALID_ID"));
        for(String query:new String[]{"?page=-1","?size=0","?size=-1","?size=101","?page=abc","?size=abc","?page=2147483648","?size=1.5"}) {
            var response=get(account.toString(),query); assertEquals(400,response.statusCode(),response.body());
            assertEquals("INVALID_PAGINATION",mapper.readTree(response.body()).get("code").asString());
            assertFalse(response.body().contains("Exception")); assertFalse(response.body().contains("SELECT"));
        }
        assertEquals(before,snapshot());
    }
}
