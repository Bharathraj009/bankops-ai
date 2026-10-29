package com.bankops.banking.account.dto;

import java.util.List;

public record AccountTransactionPage(List<AccountTransactionResponse> transactions, int page, int size,
    long totalElements, long totalPages) {}
