package com.bankops.banking.transfer.dto;

import com.bankops.banking.transfer.Transfer;
import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.UUID;

public record TransferResponse(UUID id, UUID sourceAccountId, UUID destinationAccountId,
    BigDecimal amount, String currency, String status, OffsetDateTime createdAt) {
    public static TransferResponse from(Transfer t) {
        return new TransferResponse(t.id(), t.sourceAccountId(), t.destinationAccountId(), t.amount(), t.currency(), t.status(), t.createdAt());
    }
}
