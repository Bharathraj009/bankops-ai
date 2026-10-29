package com.bankops.banking.account;

import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.UUID;

public record Account(UUID id, String accountNumber, String currency, BigDecimal balance, OffsetDateTime createdAt) {}
