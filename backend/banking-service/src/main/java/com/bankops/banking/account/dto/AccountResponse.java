package com.bankops.banking.account.dto;

import com.bankops.banking.account.Account;
import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.UUID;

public record AccountResponse(UUID id, String accountNumber, String currency, BigDecimal balance, OffsetDateTime createdAt) {
    public static AccountResponse from(Account account) {
        return new AccountResponse(account.id(), account.accountNumber(), account.currency(), account.balance(), account.createdAt());
    }
}
