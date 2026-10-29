package com.bankops.banking;

import com.bankops.banking.transfer.TransferService;
import java.math.BigDecimal;
import java.net.URI;
import java.net.http.*;
import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import tools.jackson.databind.ObjectMapper;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class TransferApiIntegrationTests extends IsolatedPostgresTest {
    @Value("${local.server.port}") int port;
    @Autowired DataSource dataSource;
    @Autowired ObjectMapper mapper;
    private final HttpClient http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build();
    private UUID account(String balance) throws Exception {
        UUID id = UUID.randomUUID();
        try (var c = dataSource.getConnection(); var s = c.prepareStatement("INSERT INTO accounts(id,account_number,balance) VALUES (?,?,?)")) {
            s.setObject(1,id); s.setString(2,id.toString()); s.setBigDecimal(3,new BigDecimal(balance)); s.executeUpdate();
        }
        return id;
    }
    private String key() { return UUID.randomUUID().toString(); }
    private String body(UUID source, UUID destination, String amount) {
        return "{\"sourceAccountId\":\""+source+"\",\"destinationAccountId\":\""+destination+"\",\"amount\":"+amount+"}";
    }
    private HttpRequest request(String key, String body) {
        var builder = operatorRequest(URI.create("http://localhost:"+port+"/api/v1/transfers"))
            .timeout(Duration.ofSeconds(20)).header("Content-Type","application/json");
        if (key != null) builder.header("Idempotency-Key",key);
        return builder.POST(HttpRequest.BodyPublishers.ofString(body)).build();
    }
    private HttpResponse<String> post(String key, String body) throws Exception {
        return http.send(request(key,body),HttpResponse.BodyHandlers.ofString());
    }
    private long count(String table, String where) throws Exception {
        try(var c=dataSource.getConnection(); var s=c.createStatement(); var r=s.executeQuery("SELECT count(*) FROM "+table+" WHERE "+where)) {
            assertTrue(r.next()); return r.getLong(1);
        }
    }
    private void balance(UUID account, String expected) throws Exception {
        try(var c=dataSource.getConnection(); var s=c.prepareStatement("SELECT balance FROM accounts WHERE id=?")) {
            s.setObject(1,account);
            try(var r=s.executeQuery()) { assertTrue(r.next()); assertEquals(new BigDecimal(expected),r.getBigDecimal(1)); }
        }
    }
    private void noEffects(UUID source, UUID destination, String key, String sourceBalance) throws Exception {
        balance(source,sourceBalance); balance(destination,"0.00");
        assertEquals(0,count("transfers","source_account_id='"+source+"'"));
        assertEquals(0,count("ledger_entries","account_id IN ('"+source+"','"+destination+"')"));
        assertEquals(0,count("idempotency_records","scope='"+TransferService.IDEMPOTENCY_SCOPE+"' AND idempotency_key='"+key+"'"));
    }
    private void completed(HttpResponse<String> response, UUID source, UUID destination, String amount, String key) throws Exception {
        var t=mapper.readTree(response.body());
        UUID id=UUID.fromString(t.get("id").asString());
        assertEquals(source.toString(),t.get("sourceAccountId").asString());
        assertEquals(destination.toString(),t.get("destinationAccountId").asString());
        assertEquals(0,new BigDecimal(amount).compareTo(t.get("amount").decimalValue()));
        assertEquals("USD",t.get("currency").asString()); assertEquals("COMPLETED",t.get("status").asString());
        assertEquals(1,count("transfers","source_account_id='"+source+"'"));
        try(var c=dataSource.getConnection(); var s=c.prepareStatement("""
            SELECT entry_type,account_id,amount,currency FROM ledger_entries WHERE transfer_id=? ORDER BY entry_type
            """)) {
            s.setObject(1,id);
            try(var r=s.executeQuery()) {
                assertTrue(r.next()); assertEquals("CREDIT",r.getString(1)); assertEquals(destination,r.getObject(2,UUID.class));
                assertEquals(0,new BigDecimal(amount).compareTo(r.getBigDecimal(3))); assertEquals("USD",r.getString(4));
                assertTrue(r.next()); assertEquals("DEBIT",r.getString(1)); assertEquals(source,r.getObject(2,UUID.class));
                assertEquals(0,new BigDecimal(amount).compareTo(r.getBigDecimal(3))); assertEquals("USD",r.getString(4)); assertFalse(r.next());
            }
        }
        try(var c=dataSource.getConnection(); var s=c.prepareStatement("SELECT request_hash,transfer_id FROM idempotency_records WHERE scope=? AND idempotency_key=?")) {
            s.setString(1,TransferService.IDEMPOTENCY_SCOPE); s.setString(2,key);
            try(var r=s.executeQuery()) { assertTrue(r.next()); assertTrue(r.getString(1).matches("[0-9a-f]{64}")); assertEquals(id,r.getObject(2,UUID.class)); assertFalse(r.next()); }
        }
    }

    @Test void executesBalancedTransferAndMovesBalancesExactly() throws Exception {
        UUID source=account("100"), destination=account("0"); String key=key();
        var response=post(key,body(source,destination,"10.25"));
        assertEquals(201,response.statusCode(),response.body()); completed(response,source,destination,"10.25",key);
        balance(source,"89.75"); balance(destination,"10.25");
    }
    @Test void normalizedMatchingRetriesReturnOriginalEvenAfterFundsAreSpent() throws Exception {
        UUID source=account("10"), destination=account("0"); String key=key();
        var first=post(key,body(source,destination,"10")); assertEquals(201,first.statusCode(),first.body());
        for(String amount:new String[]{"10.0","10.00","1e1"}) {
            var retry=post(key,body(source,destination,amount)); assertEquals(200,retry.statusCode(),retry.body());
            assertEquals(mapper.readTree(first.body()),mapper.readTree(retry.body()));
        }
        completed(first,source,destination,"10",key); balance(source,"0.00"); balance(destination,"10.00");
    }
    @Test void conflictingReuseCannotChangeOriginalTransferOrBalances() throws Exception {
        UUID source=account("100"), destination=account("0"), other=account("100"); String key=key();
        var first=post(key,body(source,destination,"10")); assertEquals(201,first.statusCode(),first.body());
        for(String changed:new String[]{body(source,destination,"11"),body(other,destination,"10"),body(source,other,"10")}) {
            var response=post(key,changed); assertEquals(409,response.statusCode(),response.body());
            assertEquals("IDEMPOTENCY_CONFLICT",mapper.readTree(response.body()).get("code").asString());
            assertFalse(response.body().contains("23514")); assertFalse(response.body().contains("fingerprint"));
        }
        completed(first,source,destination,"10",key); balance(source,"90.00"); balance(destination,"10.00"); balance(other,"100.00");
    }
    @Test void requiresValidKeyAndRejectsInvalidAndUnexpectedRequestFields() throws Exception {
        UUID source=account("100"), destination=account("0");
        for(String key:new String[]{null,""," ","x".repeat(256)}) {
            var response=post(key,body(source,destination,"10")); assertEquals(400,response.statusCode(),response.body());
        }
        for(String amount:new String[]{"0","-1","0.001","100000000000000000.00","null","\"NaN\""}) {
            var response=post(key(),body(source,destination,amount)); assertEquals(400,response.statusCode(),response.body());
        }
        for(String bad:new String[]{body(source,source,"10"),"{}","null","{", "{\"sourceAccountId\":\"bad\"}",
            body(source,destination,"10").replace("}",",\"currency\":\"EUR\"}"),
            body(source,destination,"10").replace("}",",\"balance\":500}"),
            body(source,destination,"10").replace("}",",\"status\":\"COMPLETED\"}")}) {
            var response=post(key(),bad); assertEquals(400,response.statusCode(),response.body());
        }
        balance(source,"100.00"); balance(destination,"0.00");
        assertEquals(0,count("transfers","source_account_id='"+source+"'"));
    }
    @Test void invalidAccountsAndInsufficientFundsLeaveNoClaimsOrMoneyMovement() throws Exception {
        UUID source=account("0"), destination=account("0"); String key=key();
        for(String bad:new String[]{body(UUID.randomUUID(),destination,"10"),body(source,UUID.randomUUID(),"10")}) {
            var response=post(key,bad); assertEquals(404,response.statusCode(),response.body());
            assertEquals("ACCOUNT_NOT_FOUND",mapper.readTree(response.body()).get("code").asString());
        }
        var insufficient=post(key,body(source,destination,"10")); assertEquals(422,insufficient.statusCode(),insufficient.body());
        assertEquals("INSUFFICIENT_FUNDS",mapper.readTree(insufficient.body()).get("code").asString());
        noEffects(source,destination,key,"0.00");
        UUID funded=account("100"); var successful=post(key,body(funded,destination,"10"));
        assertEquals(201,successful.statusCode(),successful.body()); completed(successful,funded,destination,"10",key);
    }
    private HttpResponse<String>[] concurrent(String keyA,String bodyA,String keyB,String bodyB) throws Exception {
        var a=http.sendAsync(request(keyA,bodyA),HttpResponse.BodyHandlers.ofString());
        var b=http.sendAsync(request(keyB,bodyB),HttpResponse.BodyHandlers.ofString());
        @SuppressWarnings("unchecked") HttpResponse<String>[] responses=new HttpResponse[]{a.get(25,TimeUnit.SECONDS),b.get(25,TimeUnit.SECONDS)};
        return responses;
    }
    @Test void concurrentMatchingDuplicatesCreateOneTransferAndOnePostingPair() throws Exception {
        UUID source=account("100"), destination=account("0"); String key=key();
        var responses=concurrent(key,body(source,destination,"60"),key,body(source,destination,"60.00"));
        assertTrue((responses[0].statusCode()==201 && responses[1].statusCode()==200)||(responses[0].statusCode()==200 && responses[1].statusCode()==201),responses[0].body()+responses[1].body());
        assertEquals(mapper.readTree(responses[0].body()),mapper.readTree(responses[1].body()));
        completed(responses[0],source,destination,"60",key); balance(source,"40.00"); balance(destination,"60.00");
    }
    @Test void concurrentConflictingRequestsHaveOneWinner() throws Exception {
        UUID source=account("100"), destination=account("0"); String key=key();
        var responses=concurrent(key,body(source,destination,"10"),key,body(source,destination,"20"));
        assertTrue((responses[0].statusCode()==201 && responses[1].statusCode()==409)||(responses[0].statusCode()==409 && responses[1].statusCode()==201),responses[0].body()+responses[1].body());
        var winner=responses[0].statusCode()==201?responses[0]:responses[1];
        BigDecimal amount=mapper.readTree(winner.body()).get("amount").decimalValue();
        completed(winner,source,destination,amount.toPlainString(),key);
        balance(source,new BigDecimal("100.00").subtract(amount).setScale(2).toPlainString()); balance(destination,amount.setScale(2).toPlainString());
    }
    @Test void concurrentDifferentKeysCannotOverspend() throws Exception {
        UUID source=account("100"), destination=account("0"); String a=key(),b=key();
        var responses=concurrent(a,body(source,destination,"80"),b,body(source,destination,"80"));
        assertTrue((responses[0].statusCode()==201 && responses[1].statusCode()==422)||(responses[0].statusCode()==422 && responses[1].statusCode()==201),responses[0].body()+responses[1].body());
        int winner=responses[0].statusCode()==201?0:1;
        completed(responses[winner],source,destination,"80",winner==0?a:b); balance(source,"20.00"); balance(destination,"80.00");
        assertEquals(1,count("idempotency_records","scope='"+TransferService.IDEMPOTENCY_SCOPE+"' AND idempotency_key IN ('"+a+"','"+b+"')"));
    }
    @Test void concurrentOppositeTransfersUseConsistentAccountLockOrder() throws Exception {
        UUID a=account("100"),b=account("100"); String first=key(),second=key();
        var responses=concurrent(first,body(a,b,"10"),second,body(b,a,"10"));
        assertEquals(201,responses[0].statusCode(),responses[0].body()); assertEquals(201,responses[1].statusCode(),responses[1].body());
        completed(responses[0],a,b,"10",first); completed(responses[1],b,a,"10",second); balance(a,"100.00"); balance(b,"100.00");
    }
    @Test void destinationOverflowIsRejectedAtomically() throws Exception {
        UUID source=account("100"),destination=account("99999999999999999.99"); String key=key();
        var response=post(key,body(source,destination,"1")); assertEquals(422,response.statusCode(),response.body());
        assertEquals("BALANCE_LIMIT_EXCEEDED",mapper.readTree(response.body()).get("code").asString());
        balance(source,"100.00"); balance(destination,"99999999999999999.99");
        assertEquals(0,count("transfers","source_account_id='"+source+"'"));
        assertEquals(0,count("idempotency_records","idempotency_key='"+key+"'"));
    }
    private void injectedFailure(boolean deferred) throws Exception {
        UUID source=account("100"),destination=account("0"); String key=key(),name="transfer_api_fault_"+UUID.randomUUID().toString().replace("-","");
        try(var c=dataSource.getConnection(); var s=c.createStatement()) {
            String condition=deferred ? "NEW.source_account_id='"+source+"' AND NEW.status='COMPLETED'"
                : "NEW.account_id='"+destination+"' AND NEW.entry_type='CREDIT'";
            s.execute("CREATE FUNCTION "+name+"() RETURNS TRIGGER LANGUAGE plpgsql AS $$ BEGIN IF "+condition+" THEN RAISE EXCEPTION 'PRIVATE_SQL_FAILURE' USING ERRCODE='23514'; END IF; RETURN NEW; END $$");
            String table=deferred?"transfers":"ledger_entries";
            try {
                s.execute((deferred ? "CREATE CONSTRAINT TRIGGER "+name+" AFTER UPDATE ON transfers DEFERRABLE INITIALLY DEFERRED"
                    : "CREATE TRIGGER "+name+" BEFORE INSERT ON ledger_entries")+" FOR EACH ROW EXECUTE FUNCTION "+name+"()");
                var response=post(key,body(source,destination,"10"));
                assertTrue(response.statusCode()==500 || response.statusCode()==503,response.statusCode()+response.body());
                assertFalse(response.body().contains("PRIVATE_SQL_FAILURE")); assertFalse(response.body().contains("23514"));
                noEffects(source,destination,key,"100.00");
            } finally { s.execute("DROP TRIGGER IF EXISTS "+name+" ON "+table); s.execute("DROP FUNCTION "+name+"()"); }
        }
        var retry=post(key,body(source,destination,"10")); assertEquals(201,retry.statusCode(),retry.body());
        completed(retry,source,destination,"10",key);
    }
    @Test void creditFailureRollsBackDebitBalanceTransferAndClaim() throws Exception { injectedFailure(false); }
    @Test void deferredCommitFailureCannotReturnSuccessAndRetryIsSafe() throws Exception { injectedFailure(true); }
}
