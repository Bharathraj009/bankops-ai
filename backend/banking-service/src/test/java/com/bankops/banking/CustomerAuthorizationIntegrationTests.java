package com.bankops.banking;

import com.bankops.banking.customer.*;
import com.bankops.banking.account.AccountService;
import com.bankops.banking.transfer.TransferService;
import java.net.URI;
import java.net.http.*;
import java.time.*;
import java.util.UUID;
import java.util.concurrent.*;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.core.context.SecurityContextHolder;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(webEnvironment=SpringBootTest.WebEnvironment.RANDOM_PORT,properties={"bankops.customer.auth.max-attempts=1000","bankops.customer.enabled=true"})
class CustomerAuthorizationIntegrationTests extends IsolatedPostgresTest {
    @LocalServerPort int port;
    @Autowired ObjectMapper json;
    @Autowired JdbcTemplate jdbc;
    @Autowired CustomerBankingService customers;
    @Autowired AccountService operators;
    @Autowired TransferService transfers;
    record Identity(UUID id,String username,String password,String token) {}
    HttpClient http;
    @BeforeEach void begin(){http=HttpClient.newHttpClient();SecurityContextHolder.clearContext();}
    @AfterEach void end(){http.close();SecurityContextHolder.clearContext();}
    HttpResponse<String> call(String method,String path,String token,String body,String key) throws Exception {
        var builder=HttpRequest.newBuilder(URI.create("http://localhost:"+port+path)).timeout(Duration.ofSeconds(20));
        if(token!=null)builder.header("Authorization","Bearer "+token);
        if(key!=null)builder.header("Idempotency-Key",key);
        builder.header("Content-Type","application/json").method(method,body==null?HttpRequest.BodyPublishers.noBody():HttpRequest.BodyPublishers.ofString(body));
        return http.send(builder.build(),HttpResponse.BodyHandlers.ofString());
    }
    JsonNode node(HttpResponse<String> r){return json.readTree(r.body());}
    Identity identity() throws Exception {
        String name="c"+UUID.randomUUID().toString().replace("-",""),password="Private-"+UUID.randomUUID();
        String body=json.writeValueAsString(java.util.Map.of("username",name,"password",password));
        var registration=call("POST","/api/v1/customer/register",null,body,null);assertEquals(201,registration.statusCode());
        var login=call("POST","/api/v1/customer/login",null,body,null);assertEquals(200,login.statusCode());
        assertTrue(login.headers().firstValue("Set-Cookie").isEmpty());
        var expiry=OffsetDateTime.parse(node(login).get("expiresAt").asString());
        assertTrue(expiry.isAfter(OffsetDateTime.now().plusMinutes(14)) && expiry.isBefore(OffsetDateTime.now().plusMinutes(16)));
        return new Identity(UUID.fromString(node(registration).get("id").asString()),name,password,node(login).get("token").asString());
    }
    UUID seed(Identity owner,int balance) {
        UUID id=UUID.randomUUID();
        // New isolated genesis fixtures only; no balance UPDATE or trigger bypass.
        jdbc.update("INSERT INTO accounts(id,account_number,currency,balance) VALUES (?,?,'USD',?)",id,"TEST-"+id,balance);
        if(owner!=null)jdbc.update("INSERT INTO customer_account_ownership(account_id,customer_id) VALUES (?,?)",id,owner.id());
        return id;
    }
    String transfer(UUID source,UUID destination,String amount){return "{\"sourceAccountId\":\""+source+"\",\"destinationAccountId\":\""+destination+"\",\"amount\":"+amount+"}";}
    String financialSnapshot(){return jdbc.queryForObject("""
        SELECT md5(coalesce((SELECT string_agg(row_to_json(a)::text,'' ORDER BY id) FROM accounts a),'')||
          coalesce((SELECT string_agg(row_to_json(t)::text,'' ORDER BY id) FROM transfers t),'')||
          coalesce((SELECT string_agg(row_to_json(l)::text,'' ORDER BY id) FROM ledger_entries l),''))
        """,String.class);}
    @Test void registrationUsesBcryptAndCannotChooseOwnershipOrRoles() throws Exception {
        var a=identity();String hash=jdbc.queryForObject("SELECT password_hash FROM customers WHERE id=?",String.class,a.id());
        assertTrue(hash.startsWith("$2a$12$"));assertNotEquals(a.password(),hash);
        assertEquals(1,jdbc.queryForObject("SELECT count(*) FROM customer_sessions WHERE token_hash=?",Integer.class,CustomerRepository.digest(a.token())));
        var created=call("POST","/api/v1/customer/accounts",a.token(),"{}",null);assertEquals(201,created.statusCode());
        UUID id=UUID.fromString(node(created).get("id").asString());
        assertEquals(0,node(created).get("balance").decimalValue().signum());
        assertTrue(node(created).get("accountNumber").asString().startsWith("CUS-"));
        assertEquals(a.id(),jdbc.queryForObject("SELECT customer_id FROM customer_account_ownership WHERE account_id=?",UUID.class,id));
        for(String body:new String[]{"{\"ownerId\":\""+UUID.randomUUID()+"\"}","{\"balance\":10}","{\"accountNumber\":\"claim-existing\"}"})
            assertEquals(400,call("POST","/api/v1/customer/accounts",a.token(),body,null).statusCode());
        assertEquals(400,call("POST","/api/v1/customer/register",null,"{\"username\":\"another-user\",\"password\":\"long-test-password\",\"role\":\"OPERATOR\"}",null).statusCode());
    }
    @Test void accountsHistoryAndOwnerlessRecordsAreIsolated() throws Exception {
        var a=identity();var b=identity();UUID own=seed(a,0),foreign=seed(b,0),legacy=seed(null,0);
        assertEquals(200,call("GET","/api/v1/customer/accounts/"+own,a.token(),null,null).statusCode());
        for(UUID other:new UUID[]{foreign,legacy,UUID.randomUUID()}) {
            assertEquals(404,call("GET","/api/v1/customer/accounts/"+other,a.token(),null,null).statusCode());
            assertEquals(404,call("GET","/api/v1/customer/accounts/"+other+"/transactions",a.token(),null,null).statusCode());
        }
        var list=node(call("GET","/api/v1/customer/accounts?size=1",a.token(),null,null));
        assertEquals(1,list.get("totalElements").asInt());assertEquals(own.toString(),list.get("accounts").get(0).get("id").asString());
        assertEquals(400,call("GET","/api/v1/customer/accounts?size=101",a.token(),null,null).statusCode());
        assertEquals(400,call("GET","/api/v1/customer/accounts/not-a-uuid",a.token(),null,null).statusCode());
    }
    @Test void transferChecksSourceBeforeAnyClaimOrPostingAndProtectsPrivateDetails() throws Exception {
        var a=identity();var b=identity();UUID own=seed(a,1000),other=seed(b,0),legacy=seed(null,0);
        String before=financialSnapshot();
        assertEquals(404,call("POST","/api/v1/customer/transfers",b.token(),transfer(own,other,"250"),"unauthorized").statusCode());
        assertEquals(404,call("POST","/api/v1/customer/transfers",a.token(),transfer(own,legacy,"250"),"legacy-destination").statusCode());
        assertEquals(before,financialSnapshot());
        var sent=call("POST","/api/v1/customer/transfers",a.token(),transfer(own,other,"250"),"same-key");assertEquals(201,sent.statusCode());
        var result=node(sent);String id=result.get("id").asString();
        assertEquals(6,result.size());assertNull(result.get("destinationAccountId"));
        assertFalse(sent.body().contains(b.username()));assertFalse(sent.body().contains(other.toString()));
        assertEquals("COMPLETED",result.get("status").asString());
        assertEquals(0,jdbc.queryForObject("SELECT balance-750 FROM accounts WHERE id=?",java.math.BigDecimal.class,own).signum());
        assertEquals(0,jdbc.queryForObject("SELECT balance-250 FROM accounts WHERE id=?",java.math.BigDecimal.class,other).signum());
        assertEquals(2,jdbc.queryForObject("SELECT count(*) FROM ledger_entries WHERE transfer_id=?",Integer.class,UUID.fromString(id)));
        assertEquals(200,call("POST","/api/v1/customer/transfers",a.token(),transfer(own,other,"250.00"),"same-key").statusCode());
        assertEquals(409,call("POST","/api/v1/customer/transfers",a.token(),transfer(own,other,"1"),"same-key").statusCode());
        assertEquals(404,call("GET","/api/v1/customer/transfers/"+id,b.token(),null,null).statusCode());
        var incoming=node(call("GET","/api/v1/customer/accounts/"+other+"/transactions",b.token(),null,null)).get("transactions").get(0);
        assertEquals(6,incoming.size());assertEquals("INCOMING",incoming.get("direction").asString());assertNull(incoming.get("sourceAccountId"));
        assertEquals("OUTGOING",node(call("GET","/api/v1/customer/accounts/"+own+"/transactions",a.token(),null,null)).get("transactions").get(0).get("direction").asString());
        before=financialSnapshot();
        assertEquals(422,call("POST","/api/v1/customer/transfers",a.token(),transfer(own,other,"9999"),"insufficient").statusCode());
        assertEquals(before,financialSnapshot());
    }
    @Test void duplicateConcurrencyAndCustomerScopedKeysRemainAtomic() throws Exception {
        var a=identity();var b=identity();UUID from=seed(a,1000),to=seed(b,1000);String body=transfer(from,to,"5");
        try(var pool=Executors.newFixedThreadPool(2)) {
            var x=pool.submit(()->call("POST","/api/v1/customer/transfers",a.token(),body,"concurrent"));
            var y=pool.submit(()->call("POST","/api/v1/customer/transfers",a.token(),body,"concurrent"));
            var first=x.get();var second=y.get();assertEquals(java.util.Set.of(200,201),java.util.Set.of(first.statusCode(),second.statusCode()));
            assertEquals(node(first).get("id").asString(),node(second).get("id").asString());
        }
        assertEquals(201,call("POST","/api/v1/customer/transfers",b.token(),transfer(to,from,"5"),"concurrent").statusCode());
        assertEquals(0,jdbc.queryForObject("SELECT balance-1000 FROM accounts WHERE id=?",java.math.BigDecimal.class,from).signum());
    }
    @Test void invalidExpiredRevokedAndWrongClassCredentialsCannotEscalate() throws Exception {
        var a=identity();UUID own=seed(a,0);
        assertEquals(401,call("GET","/api/v1/customer/accounts",null,null,null).statusCode());
        assertEquals(401,call("GET","/api/v1/customer/accounts",OPERATOR_TOKEN,null,null).statusCode());
        assertEquals(401,call("GET","/api/v1/accounts/"+own,a.token(),null,null).statusCode());
        assertEquals(401,call("GET","/api/v1/operator/me",a.token(),null,null).statusCode());
        assertEquals(200,call("GET","/api/v1/operator/me",OPERATOR_TOKEN,null,null).statusCode());
        String bad=json.writeValueAsString(java.util.Map.of("username",a.username(),"password","incorrect-password-long"));
        assertEquals(401,call("POST","/api/v1/customer/login",null,bad,null).statusCode());
        assertEquals(204,call("POST","/api/v1/customer/logout",a.token(),"{}",null).statusCode());
        assertEquals(401,call("GET","/api/v1/customer/me",a.token(),null,null).statusCode());
        var b=identity();jdbc.update("UPDATE customer_sessions SET created_at=CURRENT_TIMESTAMP-INTERVAL '2 days',expires_at=CURRENT_TIMESTAMP-INTERVAL '1 minute' WHERE token_hash=?",CustomerRepository.digest(b.token()));
        assertEquals(401,call("GET","/api/v1/customer/me",b.token(),null,null).statusCode());
        assertThrows(RuntimeException.class,()->customers.get(own));
        assertThrows(RuntimeException.class,()->operators.get(own));
        assertThrows(RuntimeException.class,()->transfers.getCustomer(UUID.randomUUID()));
        assertThrows(org.springframework.dao.DataAccessException.class,()->jdbc.update("UPDATE customer_account_ownership SET customer_id=? WHERE account_id=?",b.id(),own));
        assertEquals(a.id(),jdbc.queryForObject("SELECT customer_id FROM customer_account_ownership WHERE account_id=?",UUID.class,own));
    }
}
