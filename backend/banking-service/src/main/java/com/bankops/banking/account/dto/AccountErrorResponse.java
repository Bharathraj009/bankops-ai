package com.bankops.banking.account.dto;

import java.util.Map;

public record AccountErrorResponse(String code, String message, Map<String, String> fields) {}
