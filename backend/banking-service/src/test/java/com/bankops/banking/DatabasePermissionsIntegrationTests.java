package com.bankops.banking;

import static org.junit.jupiter.api.Assertions.*;
import java.net.URI;
import java.net.http.*;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.*;
import java.util.UUID;
import java.util.concurrent.Executors;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import com.bankops.banking.security.DatabasePrivilegeVerifier;

/** Actual ACL/authentication probes use only a newly created disposable database.
 * No development credentials, DDL cleanup, or real financial records are used. */
@SpringBootTest(webEnvironment=SpringBootTest.WebEnvironment.RANDOM_PORT,properties={"spring.datasource.hikari.maximum-pool-size=2","spring.datasource.hikari.minimum-idle=1"})
@ActiveProfiles("db-secure")
class DatabasePermissionsIntegrationTests {
    static final String MIGRATOR="bankops_migrator",RUNTIME="bankops_runtime",READER="bankops_reconciliation";
    static final String MP="migration_"+UUID.randomUUID(),RP="runtime_"+UUID.randomUUID(),AP="reader_"+UUID.randomUUID();
    static final String OP="operator_"+UUID.randomUUID();
    static String url,adminUser,adminPassword;
    @LocalServerPort int port;
    @Autowired JdbcTemplate jdbc;
    @Autowired ObjectMapper json;
    HttpClient http;
    @BeforeEach void begin(){http=HttpClient.newHttpClient();}
    @AfterEach void end(){http.close();}
    @DynamicPropertySource static void database(DynamicPropertyRegistry registry) throws Exception {
        String initial=required("BANKOPS_TEST_DB_URL");adminUser=required("BANKOPS_TEST_DB_USER");adminPassword=required("BANKOPS_TEST_DB_PASSWORD");
        // Explicit test environment only; never application datasource configuration.
        String name="permissions_"+UUID.randomUUID().toString().replace("-","");
        try(var c=DriverManager.getConnection(initial,adminUser,adminPassword);var s=c.createStatement()){s.execute("CREATE DATABASE "+name);}
        url=initial.substring(0,initial.lastIndexOf('/')+1)+name;
        try(var c=admin();var s=c.createStatement()) {
            c.setAutoCommit(false);
            s.execute(Files.readString(Path.of("../../database/roles.sql")));
            for(var pair:new String[][]{{MIGRATOR,MP},{RUNTIME,RP},{READER,AP}})
                s.execute("ALTER ROLE "+pair[0]+" LOGIN PASSWORD '"+pair[1]+"'");
            c.commit();
        }
        var flyway=Flyway.configure().dataSource(url,MIGRATOR,MP).defaultSchema("public").schemas("public").cleanDisabled(true).load();
        flyway.migrate();flyway.validate();
        try(var c=admin();var s=c.createStatement()) {
            c.setAutoCommit(false);s.execute("SET LOCAL search_path=pg_catalog,public");
            s.execute(Files.readString(Path.of("../../database/permissions.sql")));c.commit();
        }
        registry.add("spring.datasource.url",()->url);registry.add("spring.datasource.username",()->RUNTIME);registry.add("spring.datasource.password",()->RP);
        registry.add("spring.flyway.enabled",()->false);registry.add("BANKOPS_BANKING_API_TOKEN",()->OP);registry.add("bankops.customer.enabled",()->true);
    }
    static String required(String key){var s=System.getenv(key);if(s==null||s.isBlank())throw new IllegalStateException("Explicit isolated PostgreSQL required");return s;}
    static Connection admin() throws SQLException{return DriverManager.getConnection(url,adminUser,adminPassword);}
    static Connection role(String role,String password) throws SQLException{return DriverManager.getConnection(url,role,password);}
    long scalar(String query) throws Exception {try(var c=admin();var s=c.createStatement();var r=s.executeQuery(query)){r.next();return r.getLong(1);}}
    void denied(String role,String password,String statement) throws Exception {
        try(var c=role(role,password)){c.setAutoCommit(false);try(var s=c.createStatement()){
            s.execute("SET TRANSACTION READ WRITE");
            var error=assertThrows(SQLException.class,()->s.execute(statement));assertEquals("42501",error.getSQLState());
        }finally{c.rollback();}}
    }
    HttpResponse<String> call(String method,String path,String token,String body,String key) throws Exception {
        var b=HttpRequest.newBuilder(URI.create("http://127.0.0.1:"+port+"/api/v1/customer"+path));
        if(token!=null)b.header("Authorization","Bearer "+token);
        if(key!=null)b.header("Idempotency-Key",key);
        if(body!=null)b.header("Content-Type","application/json");
        return http.send(b.method(method,body==null?HttpRequest.BodyPublishers.noBody():HttpRequest.BodyPublishers.ofString(body)).build(),HttpResponse.BodyHandlers.ofString());
    }
    JsonNode node(HttpResponse<String> r)throws Exception{return json.readTree(r.body());}
    record Customer(UUID id,String token){}
    Customer customer() throws Exception {
        String body="{\"username\":\"user_"+UUID.randomUUID().toString().replace("-","")+"\",\"password\":\"synthetic-long-password\"}";
        var r=call("POST","/register",null,body,null);assertEquals(201,r.statusCode());
        var login=call("POST","/login",null,body,null);assertEquals(200,login.statusCode());
        return new Customer(UUID.fromString(node(r).get("id").asString()),node(login).get("token").asString());
    }
    UUID seed(Customer owner,int opening)throws Exception {
        UUID id=UUID.randomUUID();
        // Authorized isolated fixture genesis only, never an existing balance UPDATE.
        try(var c=admin();var s=c.createStatement()) {c.setAutoCommit(false);
            s.execute("INSERT INTO accounts(id,account_number,balance) VALUES ('"+id+"','TEST-"+id+"',"+opening+")");
            s.execute("INSERT INTO customer_account_ownership(account_id,customer_id) VALUES ('"+id+"','"+owner.id()+"')");c.commit();}
        return id;
    }
    String transfer(UUID from,UUID to,String amount){return "{\"sourceAccountId\":\""+from+"\",\"destinationAccountId\":\""+to+"\",\"amount\":"+amount+"}";}
    @Test void runtimeAuthenticatesOwnsAndTransfersWithConcurrentIdempotency() throws Exception {
        assertEquals(RUNTIME,jdbc.queryForObject("SELECT current_user",String.class));
        var a=customer();var b=customer();UUID from=seed(a,1000),to=seed(b,0);
        assertEquals(201,call("POST","/accounts",a.token(),"{}",null).statusCode());
        String body=transfer(from,to,"250"),key=UUID.randomUUID().toString();
        try(var pool=Executors.newFixedThreadPool(2)){
            var x=pool.submit(()->call("POST","/transfers",a.token(),body,key));var y=pool.submit(()->call("POST","/transfers",a.token(),body,key));
            var first=x.get();var second=y.get();assertEquals(java.util.Set.of(200,201),java.util.Set.of(first.statusCode(),second.statusCode()));
            assertEquals(node(first).get("id").asString(),node(second).get("id").asString());
        }
        assertEquals(750,scalar("SELECT balance FROM accounts WHERE id='"+from+"'"));assertEquals(250,scalar("SELECT balance FROM accounts WHERE id='"+to+"'"));
        assertEquals(404,call("GET","/accounts/"+from,b.token(),null,null).statusCode());
        assertEquals(404,call("POST","/transfers",b.token(),transfer(from,to,"1"),UUID.randomUUID().toString()).statusCode());
        assertEquals(200,call("GET","/accounts/"+to+"/transactions",b.token(),null,null).statusCode());
        assertEquals(422,call("POST","/transfers",a.token(),transfer(from,to,"9999"),UUID.randomUUID().toString()).statusCode());
        assertEquals(409,call("POST","/transfers",a.token(),transfer(from,to,"1"),key).statusCode());
        assertEquals(204,call("POST","/logout",a.token(),"{}",null).statusCode());assertEquals(401,call("GET","/me",a.token(),null,null).statusCode());
        assertEquals(0,scalar("SELECT count(*) FROM accounts a WHERE balance<>opening_balance+coalesce((SELECT sum(CASE WHEN entry_type='CREDIT' THEN amount ELSE -amount END) FROM ledger_entries l WHERE l.account_id=a.id),0)"));
    }
    @Test void runtimeCannotAlterSchemaHistoryOwnershipOrUnneededColumns() throws Exception {
        for(String command:new String[]{"CREATE TABLE public.forbidden(id int)","CREATE SCHEMA forbidden","CREATE TEMP TABLE forbidden(id int)",
            "ALTER TABLE public.accounts DISABLE TRIGGER ALL","DELETE FROM accounts WHERE false","UPDATE accounts SET account_number=account_number WHERE false",
            "UPDATE transfers SET amount=amount WHERE false","UPDATE customer_account_ownership SET customer_id=customer_id WHERE false",
            "DELETE FROM customer_sessions WHERE false","UPDATE customers SET active=false WHERE false","SELECT * FROM flyway_schema_history",
            "SET ROLE bankops_migrator","SELECT preserve_opening_balance()"}) denied(RUNTIME,RP,command);
    }
    @Test void reconciliationSelectsOnlyFourTablesEvenWithReadOnlySwitchedOff() throws Exception {
        try(var c=role(READER,AP);var s=c.createStatement();var r=s.executeQuery("SHOW default_transaction_read_only")){r.next();assertEquals("on",r.getString(1));}
        for(String table:new String[]{"accounts","transfers","ledger_entries","flyway_schema_history"}){
            try(var c=role(READER,AP);var s=c.createStatement()){s.executeQuery("SELECT * FROM "+table+" LIMIT 0");}
            for(String command:new String[]{"INSERT INTO "+table+" DEFAULT VALUES","UPDATE "+table+" SET "+(table.equals("flyway_schema_history")?"success=success":"id=id")+" WHERE false","DELETE FROM "+table+" WHERE false"})denied(READER,AP,command);
        }
        for(String command:new String[]{"SELECT * FROM customers","SELECT * FROM customer_sessions","SELECT * FROM customer_account_ownership","SELECT * FROM idempotency_records",
            "CREATE TABLE public.forbidden(id int)","CREATE TEMP TABLE forbidden(id int)","SET ROLE bankops_runtime",
            "SELECT create_idempotent_transfer('a','b','c',gen_random_uuid(),gen_random_uuid(),1,'USD')"})denied(READER,AP,command);
    }
    @Test void agentAndMonitoringHaveNoLoginOrFinancialAccess() throws Exception {
        for(String principal:new String[]{"bankops_agent","bankops_monitoring"}){
            assertThrows(SQLException.class,()->role(principal,"not-a-credential"));
            try(var c=admin();var s=c.createStatement()) {c.setAutoCommit(false);s.execute("SET ROLE "+principal);
                try {var error=assertThrows(SQLException.class,()->s.execute("UPDATE public.accounts SET balance=balance WHERE false"));assertEquals("42501",error.getSQLState());}finally{c.rollback();}}
            assertEquals(0,scalar("SELECT count(*) FROM pg_roles WHERE rolname='"+principal+"' AND rolcanlogin"));
            assertEquals(0,scalar("SELECT count(*) FROM pg_database WHERE datname=current_database() AND has_database_privilege('"+principal+"',oid,'CONNECT,TEMP,CREATE')"));
            for(String table:new String[]{"accounts","transfers","ledger_entries","customers","customer_sessions"})
                assertEquals(0,scalar("SELECT CASE WHEN has_table_privilege('"+principal+"','"+table+"','SELECT,INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER') THEN 1 ELSE 0 END"));
        }
    }
    @Test void migrationRoleOwnsObjectsAndFutureObjectsRemainPrivate() throws Exception {
        var flyway=Flyway.configure().dataSource(url,MIGRATOR,MP).cleanDisabled(true).load();flyway.validate();assertEquals(6,flyway.info().applied().length);
        assertEquals(0,scalar("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND pg_get_userbyid(c.relowner)<>'bankops_migrator'"));
        try(var c=role(MIGRATOR,MP);var s=c.createStatement()){c.setAutoCommit(false);
            s.execute("CREATE TABLE public.future_private(id int)");s.execute("CREATE FUNCTION public.future_private() RETURNS int LANGUAGE sql AS 'SELECT 1'");
            try(var r=s.executeQuery("SELECT has_table_privilege('bankops_runtime','public.future_private','SELECT'),has_function_privilege('bankops_reconciliation','public.future_private()','EXECUTE')")){
                r.next();assertFalse(r.getBoolean(1));assertFalse(r.getBoolean(2));}c.rollback();}
        var adminJdbc=new JdbcTemplate(new DriverManagerDataSource(url,adminUser,adminPassword));
        assertThrows(IllegalStateException.class,()->new DatabasePrivilegeVerifier(adminJdbc).verify());
        // Reapplying reviewed ACLs is repeatable and changes no banking rows.
        try(var c=admin();var s=c.createStatement()){c.setAutoCommit(false);s.execute(Files.readString(Path.of("../../database/permissions.sql")));c.commit();}
    }
    @Test void runtimeCannotCommitUnmatchedBalancesOrCompletedTransfers() throws Exception {
        var a=customer();var b=customer();UUID from=seed(a,10),to=seed(b,0);
        try(var c=role(RUNTIME,RP);var s=c.createStatement()){c.setAutoCommit(false);
            s.execute("UPDATE accounts SET balance=9 WHERE id='"+from+"'");
            var error=assertThrows(SQLException.class,c::commit);assertEquals("23514",error.getSQLState());c.rollback();}
        try(var c=role(RUNTIME,RP);var s=c.createStatement()){c.setAutoCommit(false);
            s.execute("INSERT INTO transfers(id,source_account_id,destination_account_id,amount) VALUES(gen_random_uuid(),'"+from+"','"+to+"',1)");
            s.execute("UPDATE transfers SET status='COMPLETED' WHERE source_account_id='"+from+"'");
            var error=assertThrows(SQLException.class,c::commit);assertEquals("23514",error.getSQLState());c.rollback();}
        assertEquals(10,scalar("SELECT balance FROM accounts WHERE id='"+from+"'"));
    }
}
