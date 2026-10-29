package com.bankops.banking;

import com.bankops.banking.transfer.TransferService;
import java.math.BigDecimal;
import java.net.URI;
import java.net.http.*;
import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import javax.sql.DataSource;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import tools.jackson.databind.ObjectMapper;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(webEnvironment=SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("dev")
class DevFundingIntegrationTests extends IsolatedPostgresTest {
    private static final UUID SYSTEM=UUID.fromString("77777777-7777-4777-8777-777777777777");
    @DynamicPropertySource static void funding(DynamicPropertyRegistry registry) {
        registry.add("bankops.dev.funding-account-id",SYSTEM::toString);
    }
    @Value("${local.server.port}") int port;
    @Autowired DataSource dataSource;
    @Autowired ObjectMapper mapper;
    private final HttpClient http=HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build();
    @BeforeEach void provisionTestReserve() throws Exception {
        // Test fixture genesis balance, not application funding or a balance update.
        try(var c=dataSource.getConnection(); var s=c.prepareStatement("INSERT INTO accounts(id,account_number,balance) VALUES (?,'DEV-SYSTEM-FUNDING',1000000) ON CONFLICT(id) DO NOTHING")) {
            s.setObject(1,SYSTEM); s.executeUpdate();
        }
    }
    private UUID target() throws Exception {
        UUID id=UUID.randomUUID();
        try(var c=dataSource.getConnection(); var s=c.prepareStatement("INSERT INTO accounts(id,account_number) VALUES (?,?)")) {
            s.setObject(1,id); s.setString(2,id.toString()); s.executeUpdate();
        }
        return id;
    }
    private BigDecimal balance(UUID id) throws Exception {
        try(var c=dataSource.getConnection(); var s=c.prepareStatement("SELECT balance FROM accounts WHERE id=?")) {
            s.setObject(1,id); try(var r=s.executeQuery()) { assertTrue(r.next()); return r.getBigDecimal(1); }
        }
    }
    private String key() { return UUID.randomUUID().toString(); }
    private HttpRequest request(String id,String key,String body) {
        var builder=operatorRequest(URI.create("http://localhost:"+port+"/api/v1/dev/accounts/"+id+"/fund"))
            .timeout(Duration.ofSeconds(15)).header("Content-Type","application/json");
        if(key!=null) builder.header("Idempotency-Key",key);
        return builder.POST(HttpRequest.BodyPublishers.ofString(body)).build();
    }
    private HttpResponse<String> fund(UUID target,String key,String amount) throws Exception {
        return http.send(request(target.toString(),key,"{\"amount\":"+amount+"}"),HttpResponse.BodyHandlers.ofString());
    }
    private long count(String table,String where) throws Exception {
        try(var c=dataSource.getConnection(); var s=c.createStatement(); var r=s.executeQuery("SELECT count(*) FROM "+table+" WHERE "+where)) {
            assertTrue(r.next()); return r.getLong(1);
        }
    }
    private void noEffects(UUID target,String key,BigDecimal before) throws Exception {
        assertEquals(before,balance(SYSTEM)); assertEquals(new BigDecimal("0.00"),balance(target));
        assertEquals(0,count("transfers","destination_account_id='"+target+"'"));
        assertEquals(0,count("ledger_entries","account_id='"+target+"'"));
        assertEquals(0,count("idempotency_records","scope='"+TransferService.FUNDING_SCOPE+"' AND idempotency_key='"+key+"'"));
    }
    private void funded(HttpResponse<String> response,UUID target,String amount,String key,BigDecimal before) throws Exception {
        var json=mapper.readTree(response.body()); UUID transfer=UUID.fromString(json.get("id").asString());
        assertEquals(SYSTEM.toString(),json.get("sourceAccountId").asString()); assertEquals(target.toString(),json.get("destinationAccountId").asString());
        assertEquals("COMPLETED",json.get("status").asString()); assertEquals("USD",json.get("currency").asString());
        BigDecimal value=new BigDecimal(amount).setScale(2);
        assertEquals(value,balance(target)); assertEquals(before.subtract(value),balance(SYSTEM));
        assertEquals(1,count("transfers","destination_account_id='"+target+"'"));
        assertEquals(2,count("ledger_entries","transfer_id='"+transfer+"'"));
        assertEquals(1,count("ledger_entries","transfer_id='"+transfer+"' AND account_id='"+SYSTEM+"' AND entry_type='DEBIT' AND amount="+value));
        assertEquals(1,count("ledger_entries","transfer_id='"+transfer+"' AND account_id='"+target+"' AND entry_type='CREDIT' AND amount="+value));
        assertEquals(1,count("idempotency_records","scope='"+TransferService.FUNDING_SCOPE+"' AND idempotency_key='"+key+"' AND transfer_id='"+transfer+"'"));
        try(var c=dataSource.getConnection(); var s=c.prepareStatement("SELECT opening_balance FROM accounts WHERE id=?")) {
            s.setObject(1,target); try(var r=s.executeQuery()) { assertTrue(r.next()); assertEquals(new BigDecimal("0.00"),r.getBigDecimal(1)); }
        }
    }
    @Test void fundingUsesBalancedPostingsAndMatchingRetryMovesMoneyOnce() throws Exception {
        UUID target=target(); String key=key(); BigDecimal before=balance(SYSTEM);
        var first=fund(target,key,"10.25"); assertEquals(201,first.statusCode(),first.body());
        var retry=fund(target,key,"10.25"); assertEquals(200,retry.statusCode(),retry.body());
        assertEquals(mapper.readTree(first.body()),mapper.readTree(retry.body())); funded(first,target,"10.25",key,before);
    }
    @Test void conflictingAmountsAndTargetsAreRejected() throws Exception {
        UUID target=target(),other=target(); String key=key(); BigDecimal before=balance(SYSTEM);
        var first=fund(target,key,"10"); assertEquals(201,first.statusCode(),first.body());
        assertEquals(409,fund(target,key,"11").statusCode()); assertEquals(409,fund(other,key,"10").statusCode());
        funded(first,target,"10",key,before); assertEquals(new BigDecimal("0.00"),balance(other));
    }
    @Test void validatesAmountsKeysIdsAndRejectsClientSourceAndCurrency() throws Exception {
        UUID target=target(); BigDecimal before=balance(SYSTEM);
        for(String amount:new String[]{"0","-1","0.001","null","100000000000000000","\"NaN\""}) assertEquals(400,fund(target,key(),amount).statusCode());
        for(String key:new String[]{null,""," ","x".repeat(256)}) assertEquals(400,fund(target,key,"1").statusCode());
        for(String body:new String[]{"{}","{","{\"amount\":1,\"sourceAccountId\":\""+SYSTEM+"\"}","{\"amount\":1,\"balance\":1}","{\"amount\":1,\"currency\":\"EUR\"}"}) {
            assertEquals(400,http.send(request(target.toString(),key(),body),HttpResponse.BodyHandlers.ofString()).statusCode());
        }
        var malformed=http.send(request("PRIVATE_BAD_ID",key(),"{\"amount\":1}"),HttpResponse.BodyHandlers.ofString());
        assertEquals(400,malformed.statusCode()); assertEquals("INVALID_ACCOUNT_ID",mapper.readTree(malformed.body()).get("code").asString());
        assertEquals(404,fund(UUID.randomUUID(),key(),"1").statusCode());
        assertEquals(400,fund(SYSTEM,key(),"1").statusCode()); noEffects(target,key(),before);
    }
    @Test void cannotCreateMoneyWhenFiniteReserveIsExhausted() throws Exception {
        UUID target=target(); String key=key(); BigDecimal before=balance(SYSTEM);
        var response=fund(target,key,before.add(BigDecimal.ONE).toPlainString());
        assertEquals(422,response.statusCode(),response.body()); assertEquals("INSUFFICIENT_FUNDS",mapper.readTree(response.body()).get("code").asString());
        noEffects(target,key,before);
    }
    @Test void concurrentMatchingFundingRequestsCreateOneTransfer() throws Exception {
        UUID target=target(); String key=key(); BigDecimal before=balance(SYSTEM);
        var a=http.sendAsync(request(target.toString(),key,"{\"amount\":20}"),HttpResponse.BodyHandlers.ofString());
        var b=http.sendAsync(request(target.toString(),key,"{\"amount\":20.00}"),HttpResponse.BodyHandlers.ofString());
        var first=a.get(20,TimeUnit.SECONDS); var second=b.get(20,TimeUnit.SECONDS);
        assertTrue((first.statusCode()==201&&second.statusCode()==200)||(first.statusCode()==200&&second.statusCode()==201),first.body()+second.body());
        assertEquals(mapper.readTree(first.body()),mapper.readTree(second.body())); funded(first,target,"20",key,before);
    }
    @Test void concurrentConflictingFundingRequestsHaveOneWinner() throws Exception {
        UUID target=target(); String key=key(); BigDecimal before=balance(SYSTEM);
        var a=http.sendAsync(request(target.toString(),key,"{\"amount\":10}"),HttpResponse.BodyHandlers.ofString());
        var b=http.sendAsync(request(target.toString(),key,"{\"amount\":20}"),HttpResponse.BodyHandlers.ofString());
        var first=a.get(20,TimeUnit.SECONDS); var second=b.get(20,TimeUnit.SECONDS);
        assertTrue((first.statusCode()==201&&second.statusCode()==409)||(first.statusCode()==409&&second.statusCode()==201),first.body()+second.body());
        var winner=first.statusCode()==201?first:second;
        funded(winner,target,mapper.readTree(winner.body()).get("amount").decimalValue().toPlainString(),key,before);
    }
    private void fault(boolean deferred) throws Exception {
        UUID target=target(); String key=key(),name="funding_fault_"+UUID.randomUUID().toString().replace("-",""); BigDecimal before=balance(SYSTEM);
        try(var c=dataSource.getConnection(); var s=c.createStatement()) {
            String condition=deferred?"NEW.destination_account_id='"+target+"' AND NEW.status='COMPLETED'":"NEW.account_id='"+target+"' AND NEW.entry_type='CREDIT'";
            s.execute("CREATE FUNCTION "+name+"() RETURNS TRIGGER LANGUAGE plpgsql AS $$ BEGIN IF "+condition+" THEN RAISE EXCEPTION 'PRIVATE_FUNDING_FAILURE' USING ERRCODE='23514'; END IF; RETURN NEW; END $$");
            String table=deferred?"transfers":"ledger_entries";
            try {
                s.execute((deferred?"CREATE CONSTRAINT TRIGGER "+name+" AFTER UPDATE ON transfers DEFERRABLE INITIALLY DEFERRED":"CREATE TRIGGER "+name+" BEFORE INSERT ON ledger_entries")+" FOR EACH ROW EXECUTE FUNCTION "+name+"()");
                var response=fund(target,key,"10"); assertTrue(response.statusCode()==500||response.statusCode()==503,response.body());
                assertFalse(response.body().contains("PRIVATE_FUNDING_FAILURE")); noEffects(target,key,before);
            } finally { s.execute("DROP TRIGGER IF EXISTS "+name+" ON "+table); s.execute("DROP FUNCTION "+name+"()"); }
        }
        var retry=fund(target,key,"10"); assertEquals(201,retry.statusCode(),retry.body()); funded(retry,target,"10",key,before);
    }
    @Test void failedCreditRollsBackReserveDebitAndClaim() throws Exception { fault(false); }
    @Test void deferredFailureRollsBackFundingAndCanBeRetried() throws Exception { fault(true); }
}
