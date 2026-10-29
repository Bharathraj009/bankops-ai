package com.bankops.banking.transfer;

import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.UUID;

public record Transfer(UUID id, UUID sourceAccountId, UUID destinationAccountId, BigDecimal amount,
    String currency, String status, OffsetDateTime createdAt) {}
