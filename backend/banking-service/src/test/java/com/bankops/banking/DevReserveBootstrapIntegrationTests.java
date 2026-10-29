package com.bankops.banking;

import com.bankops.banking.dev.DevReserveBootstrap;
import com.bankops.banking.transfer.TransferService;
import java.math.BigDecimal;
import java.util.UUID;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.CyclicBarrier;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.RepeatedTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(properties={"bankops.dev.reserve-bootstrap.enabled=true",
    "bankops.dev.funding-account-id=66666666-6666-4666-8666-666666666666"})
@ActiveProfiles("dev")
class DevReserveBootstrapIntegrationTests extends IsolatedPostgresTest {
    private static final UUID STARTUP=UUID.fromString("66666666-6666-4666-8666-666666666666");
    @Autowired DevReserveBootstrap bootstrap;
    @Autowired TransferService transfers;
    @Autowired DataSource dataSource;
    private long count(UUID id) throws Exception {
        try(var c=dataSource.getConnection(); var s=c.prepareStatement("SELECT count(*) FROM accounts WHERE id=?")) {
            s.setObject(1,id); try(var r=s.executeQuery()) { assertTrue(r.next()); return r.getLong(1); }
        }
    }
    private void reserve(UUID id,String balance,String opening) throws Exception {
        try(var c=dataSource.getConnection(); var s=c.prepareStatement("SELECT account_number,currency,balance,opening_balance FROM accounts WHERE id=?")) {
            s.setObject(1,id); try(var r=s.executeQuery()) {
                assertTrue(r.next()); assertEquals("DEV-FUNDING-"+id,r.getString(1)); assertEquals("USD",r.getString(2));
                assertEquals(new BigDecimal(balance),r.getBigDecimal(3)); assertEquals(new BigDecimal(opening),r.getBigDecimal(4));
            }
        }
    }
    private void noPostings(UUID id) throws Exception {
        try(var c=dataSource.getConnection(); var s=c.prepareStatement("SELECT count(*) FROM ledger_entries WHERE account_id=?")) {
            s.setObject(1,id); try(var r=s.executeQuery()) { assertTrue(r.next()); assertEquals(0,r.getLong(1)); }
        }
    }
    @Test void startupInitializesReserveAndRepeatDoesNotReplenishAfterFunding() throws Exception {
        reserve(STARTUP,"1000000.00","1000000.00"); noPostings(STARTUP);
        UUID target=UUID.randomUUID();
        try(var c=dataSource.getConnection(); var s=c.prepareStatement("INSERT INTO accounts(id,account_number) VALUES (?,?)")) {
            s.setObject(1,target); s.setString(2,target.toString()); s.executeUpdate();
        }
        asOperator(()->transfers.fund(UUID.randomUUID().toString(),STARTUP,target,new BigDecimal("25.00")));
        assertFalse(bootstrap.initialize(STARTUP,new BigDecimal("1000000.00")));
        reserve(STARTUP,"999975.00","1000000.00");
        assertThrows(IllegalStateException.class,()->bootstrap.initialize(STARTUP,new BigDecimal("2000000.00")));
        reserve(STARTUP,"999975.00","1000000.00");
    }
    @Test void initializationIsRepeatableAndCreatesNoFakeLedgerEntries() throws Exception {
        UUID id=UUID.randomUUID();
        assertTrue(bootstrap.initialize(id,new BigDecimal("100.25")));
        assertFalse(bootstrap.initialize(id,new BigDecimal("100.25")));
        assertEquals(1,count(id)); reserve(id,"100.25","100.25"); noPostings(id);
    }
    @Test void invalidAmountsAndExistingOrdinaryAccountAreNotChanged() throws Exception {
        UUID id=UUID.randomUUID();
        for(BigDecimal amount:new BigDecimal[]{null,BigDecimal.ZERO,new BigDecimal("-1"),new BigDecimal("0.001"),new BigDecimal("100000000000000000")}) {
            assertThrows(IllegalArgumentException.class,()->bootstrap.initialize(id,amount)); assertEquals(0,count(id));
        }
        try(var c=dataSource.getConnection(); var s=c.prepareStatement("INSERT INTO accounts(id,account_number) VALUES (?,?)")) {
            s.setObject(1,id); s.setString(2,"ordinary-"+id); s.executeUpdate();
        }
        assertThrows(IllegalStateException.class,()->bootstrap.initialize(id,new BigDecimal("100")));
        try(var c=dataSource.getConnection(); var s=c.prepareStatement("SELECT balance,opening_balance FROM accounts WHERE id=?")) {
            s.setObject(1,id); try(var r=s.executeQuery()) { assertTrue(r.next()); assertEquals(new BigDecimal("0.00"),r.getBigDecimal(1)); assertEquals(new BigDecimal("0.00"),r.getBigDecimal(2)); }
        }
    }
    @RepeatedTest(100) void concurrentInitializationCreatesExactlyOneReserve() throws Exception {
        UUID id=UUID.randomUUID();
        var start=new CyclicBarrier(2);
        try(var executor=Executors.newFixedThreadPool(2)) {
            var first=executor.submit(()->{ start.await(5,TimeUnit.SECONDS); return bootstrap.initialize(id,new BigDecimal("100")); });
            var second=executor.submit(()->{ start.await(5,TimeUnit.SECONDS); return bootstrap.initialize(id,new BigDecimal("100")); });
            assertNotEquals(first.get(10,TimeUnit.SECONDS),second.get(10,TimeUnit.SECONDS));
        }
        assertEquals(1,count(id)); reserve(id,"100.00","100.00"); noPostings(id);
    }
    @Test void deferredFailureRollsBackReserveAndRepeatCanSucceed() throws Exception {
        UUID id=UUID.randomUUID(); String name="reserve_fault_"+UUID.randomUUID().toString().replace("-","");
        try(var c=dataSource.getConnection(); var s=c.createStatement()) {
            s.execute("CREATE FUNCTION "+name+"() RETURNS TRIGGER LANGUAGE plpgsql AS $$ BEGIN IF NEW.id='"+id+"' THEN RAISE EXCEPTION 'Reserve probe failed' USING ERRCODE='23514'; END IF; RETURN NEW; END $$");
            try {
                s.execute("CREATE CONSTRAINT TRIGGER "+name+" AFTER INSERT ON accounts DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION "+name+"()");
                assertThrows(RuntimeException.class,()->bootstrap.initialize(id,new BigDecimal("100")));
                assertEquals(0,count(id)); noPostings(id);
            } finally { s.execute("DROP TRIGGER IF EXISTS "+name+" ON accounts"); s.execute("DROP FUNCTION "+name+"()"); }
        }
        assertTrue(bootstrap.initialize(id,new BigDecimal("100"))); reserve(id,"100.00","100.00"); noPostings(id);
    }

    @Test void accountNumberCollisionWithAnotherIdCannotBeAdoptedOrFunded() throws Exception {
        UUID requested=UUID.randomUUID(),existing=UUID.randomUUID();
        try(var c=dataSource.getConnection(); var s=c.prepareStatement("INSERT INTO accounts(id,account_number) VALUES (?,?)")) {
            s.setObject(1,existing); s.setString(2,"DEV-FUNDING-"+requested); s.executeUpdate();
        }
        assertThrows(IllegalStateException.class,()->bootstrap.initialize(requested,new BigDecimal("100")));
        assertEquals(0,count(requested)); assertEquals(1,count(existing)); noPostings(existing);
        try(var c=dataSource.getConnection(); var s=c.prepareStatement("SELECT balance,opening_balance FROM accounts WHERE id=?")) {
            s.setObject(1,existing); try(var r=s.executeQuery()) {
                assertTrue(r.next()); assertEquals(new BigDecimal("0.00"),r.getBigDecimal(1)); assertEquals(new BigDecimal("0.00"),r.getBigDecimal(2));
            }
        }
    }

    @Test void concurrentDifferentOpeningBalancesRejectLoserWithoutReplenishing() throws Exception {
        UUID id=UUID.randomUUID(); var start=new CyclicBarrier(2);
        try(var executor=Executors.newFixedThreadPool(2)) {
            var first=executor.submit(()->{ start.await(5,TimeUnit.SECONDS); try { bootstrap.initialize(id,new BigDecimal("100")); return true; } catch(IllegalStateException conflict) { return false; } });
            var second=executor.submit(()->{ start.await(5,TimeUnit.SECONDS); try { bootstrap.initialize(id,new BigDecimal("200")); return true; } catch(IllegalStateException conflict) { return false; } });
            boolean firstWon=first.get(10,TimeUnit.SECONDS),secondWon=second.get(10,TimeUnit.SECONDS);
            assertNotEquals(firstWon,secondWon);
            reserve(id,firstWon?"100.00":"200.00",firstWon?"100.00":"200.00");
        }
        assertEquals(1,count(id)); noPostings(id);
    }
}
