package com.bankops.banking.account.dto;

import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.UUID;

public record AccountTransactionResponse(UUID transferId, OffsetDateTime timestamp, String direction,
    BigDecimal amount, String currency, String status) {}
