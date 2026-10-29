package com.bankops.banking;

import java.sql.DriverManager;
import java.util.UUID;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class CustomerMigrationIntegrationTests {
    @Test void additiveV6LeavesLegacyFinancialRowsOwnerlessAndUnchanged() throws Exception {
        String schema="customer_migration_"+UUID.randomUUID().toString().replace("-","");
        String url=System.getenv("BANKOPS_TEST_DB_URL"),user=System.getenv("BANKOPS_TEST_DB_USER"),password=System.getenv("BANKOPS_TEST_DB_PASSWORD");
        assertNotNull(url);assertTrue(url.contains("bankops_test"));
        Flyway.configure().dataSource(url,user,password).schemas(schema).defaultSchema(schema).target("5").load().migrate();
        try(var c=DriverManager.getConnection(url,user,password);var s=c.createStatement()) {
            c.setSchema(schema);
            s.execute("INSERT INTO accounts(id,account_number,currency,balance) VALUES (gen_random_uuid(),'LEGACY-UNCHANGED','USD',25)");
            String before;
            try(var r=s.executeQuery("SELECT row_to_json(a)::text FROM accounts a")){assertTrue(r.next());before=r.getString(1);}
            Flyway.configure().dataSource(url,user,password).schemas(schema).defaultSchema(schema).target("6").load().migrate();
            try(var r=s.executeQuery("SELECT row_to_json(a)::text FROM accounts a")){assertTrue(r.next());assertEquals(before,r.getString(1));}
            try(var r=s.executeQuery("SELECT count(*) FROM customer_account_ownership")){assertTrue(r.next());assertEquals(0,r.getInt(1));}
            try(var r=s.executeQuery("SELECT count(*) FROM customers")){assertTrue(r.next());assertEquals(0,r.getInt(1));}
        }
    }
}
