package com.bankops.banking.transfer;

import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;
import java.util.Optional;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class TransferRepository {
    public record LockedAccount(UUID id, BigDecimal balance) {}
    private final JdbcTemplate jdbc;
    public TransferRepository(JdbcTemplate jdbc) { this.jdbc = jdbc; }

    public Optional<Transfer> findById(UUID id) {
        return jdbc.query("SELECT id,source_account_id,destination_account_id,amount,currency,status,created_at FROM transfers WHERE id=?",
            (rs, row) -> new Transfer(rs.getObject("id", UUID.class), rs.getObject("source_account_id", UUID.class),
                rs.getObject("destination_account_id", UUID.class), rs.getBigDecimal("amount"), rs.getString("currency"),
                rs.getString("status"), rs.getObject("created_at", OffsetDateTime.class)), id).stream().findFirst();
    }

    public List<LockedAccount> lockAccounts(UUID source, UUID destination) {
        // Lock before the V5 insert's foreign-key locks to avoid concurrent lock upgrades.
        return jdbc.query("SELECT id,balance FROM accounts WHERE id IN (?,?) ORDER BY id FOR UPDATE",
            (rs, row) -> new LockedAccount(rs.getObject("id", UUID.class), rs.getBigDecimal("balance")), source, destination);
    }
    public UUID claim(String scope, String key, String fingerprint, UUID source, UUID destination, BigDecimal amount) {
        return jdbc.queryForObject("SELECT create_idempotent_transfer(?,?,?,?,?,?,'USD')", UUID.class,
            scope, key, fingerprint, source, destination, amount);
    }
    public Transfer lockTransfer(UUID id) {
        return jdbc.queryForObject("SELECT id,source_account_id,destination_account_id,amount,currency,status,created_at FROM transfers WHERE id=? FOR UPDATE",
            (rs, row) -> new Transfer(rs.getObject("id", UUID.class), rs.getObject("source_account_id", UUID.class),
                rs.getObject("destination_account_id", UUID.class), rs.getBigDecimal("amount"), rs.getString("currency"),
                rs.getString("status"), rs.getObject("created_at", OffsetDateTime.class)), id);
    }
    public int postingCount(UUID transferId) {
        return jdbc.queryForObject("SELECT count(*) FROM ledger_entries WHERE transfer_id=?", Integer.class, transferId);
    }
    public void post(Transfer t) {
        // V3 alone moves balances. The service must never update balances separately.
        jdbc.update("""
            INSERT INTO ledger_entries(id,transfer_id,account_id,entry_type,amount,currency)
            VALUES (?,?,?,'DEBIT',?,'USD'),(?,?,?,'CREDIT',?,'USD')
            """, UUID.randomUUID(), t.id(), t.sourceAccountId(), t.amount(),
            UUID.randomUUID(), t.id(), t.destinationAccountId(), t.amount());
    }
    public void complete(UUID id) {
        if (jdbc.update("UPDATE transfers SET status='COMPLETED' WHERE id=? AND status='PENDING'", id) != 1) {
            throw new IllegalStateException("Transfer changed while locked");
        }
    }
}
