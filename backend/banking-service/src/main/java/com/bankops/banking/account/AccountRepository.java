package com.bankops.banking.account;

import java.time.OffsetDateTime;
import java.util.UUID;
import java.util.Optional;
import java.util.List;
import com.bankops.banking.account.dto.AccountTransactionResponse;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class AccountRepository {
    private final JdbcTemplate jdbc;

    public AccountRepository(JdbcTemplate jdbc) { this.jdbc = jdbc; }

    public long transactionCount(UUID accountId) {
        return jdbc.queryForObject("""
            SELECT count(*) FROM ledger_entries l JOIN transfers t ON t.id=l.transfer_id
            WHERE l.account_id=? AND t.status='COMPLETED'
            """, Long.class, accountId);
    }

    public List<AccountTransactionResponse> transactions(UUID accountId, int size, long offset) {
        // Amount, currency, direction and timestamp come from the immutable posting.
        return jdbc.query("""
            SELECT l.transfer_id,l.created_at,
                CASE WHEN l.entry_type='DEBIT' THEN 'OUTGOING' ELSE 'INCOMING' END AS direction,
                l.amount,l.currency,t.status
            FROM ledger_entries l JOIN transfers t ON t.id=l.transfer_id
            WHERE l.account_id=? AND t.status='COMPLETED'
            ORDER BY l.created_at DESC,l.transfer_id DESC
            LIMIT ? OFFSET ?
            """, (rs, row) -> new AccountTransactionResponse(rs.getObject("transfer_id", UUID.class),
                rs.getObject("created_at", OffsetDateTime.class), rs.getString("direction"),
                rs.getBigDecimal("amount"), rs.getString("currency"), rs.getString("status")), accountId, size, offset);
    }

    public Optional<Account> findById(UUID id) {
        return jdbc.query("SELECT id, account_number, currency, balance, created_at FROM accounts WHERE id=?",
            (rs, row) -> new Account(rs.getObject("id", UUID.class), rs.getString("account_number"),
                rs.getString("currency"), rs.getBigDecimal("balance"), rs.getObject("created_at", OffsetDateTime.class)),
            id).stream().findFirst();
    }

    public Account create(UUID id, String accountNumber, String currency) {
        // Opening balance is derived by V3. No client value can reach either balance.
        return jdbc.queryForObject("""
            INSERT INTO accounts(id, account_number, currency, balance)
            VALUES (?, ?, ?, 0)
            RETURNING id, account_number, currency, balance, created_at
            """, (rs, row) -> new Account(rs.getObject("id", UUID.class), rs.getString("account_number"),
                rs.getString("currency"), rs.getBigDecimal("balance"), rs.getObject("created_at", OffsetDateTime.class)),
            id, accountNumber, currency);
    }
}
