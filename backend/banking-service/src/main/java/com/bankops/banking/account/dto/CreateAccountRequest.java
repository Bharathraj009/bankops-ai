package com.bankops.banking.account.dto;

import com.fasterxml.jackson.annotation.JsonAnySetter;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record CreateAccountRequest(
    @NotBlank(message = "Account number is required")
    @Size(max = 64, message = "Account number must contain at most 64 characters") String accountNumber,
    @Pattern(regexp = "USD", message = "Currency must be USD") String currency
) {
    public CreateAccountRequest {
        if (currency == null) currency = "USD";
    }

    // Enforce an allowlist even when the application mapper ignores unknown fields.
    // In particular, neither balance nor openingBalance nor id is client writable.
    @JsonAnySetter
    public void rejectUnknownField(String field, Object value) {
        throw new IllegalArgumentException("Unknown account creation field");
    }
}
