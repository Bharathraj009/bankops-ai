package com.bankops.banking.dev;

import java.math.BigDecimal;
import java.util.UUID;
import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Profile("dev & !prod & !production & !test")
public class DevReserveBootstrap {
    private final JdbcTemplate jdbc;
    public DevReserveBootstrap(JdbcTemplate jdbc) { this.jdbc=jdbc; }

    @Transactional
    public boolean initialize(UUID id, BigDecimal initialBalance) {
        if (id==null || initialBalance==null || initialBalance.signum()<=0 ||
            initialBalance.stripTrailingZeros().scale()>2 ||
            initialBalance.compareTo(new BigDecimal("99999999999999999.99"))>0) {
            throw new IllegalArgumentException("Reserve requires a UUID and a positive USD opening balance with cent precision");
        }
        String number="DEV-FUNDING-"+id;
        // Genesis account creation only: V3 derives opening_balance from this INSERT.
        // Never UPDATE an existing balance, replenish a reserve, or synthesize postings.
        // Both id and account_number are unique. Handle either concurrent conflict,
        // then require the exact configured identity and immutable opening balance.
        boolean created=jdbc.update("INSERT INTO accounts(id,account_number,currency,balance) VALUES (?,?,'USD',?) ON CONFLICT DO NOTHING",
            id,number,initialBalance)==1;
        var matches=jdbc.query("""
            SELECT account_number=? AND currency='USD' AND opening_balance=?
            FROM accounts WHERE id=? FOR UPDATE
            """, (rs,row)->rs.getBoolean(1),number,initialBalance,id);
        if (matches.size()!=1 || !matches.get(0)) throw new IllegalStateException("Existing account is incompatible with the configured development reserve");
        return created;
    }
}
