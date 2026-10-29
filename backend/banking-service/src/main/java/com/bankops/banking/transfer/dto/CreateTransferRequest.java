package com.bankops.banking.transfer.dto;

import com.fasterxml.jackson.annotation.JsonAnySetter;
import com.fasterxml.jackson.annotation.JsonIgnore;
import jakarta.validation.constraints.*;
import java.math.BigDecimal;
import java.util.UUID;

public record CreateTransferRequest(
    @NotNull UUID sourceAccountId, @NotNull UUID destinationAccountId,
    @NotNull @DecimalMin(value = "0", inclusive = false) @Digits(integer = 17, fraction = 2) BigDecimal amount
) {
    @JsonIgnore
    @AssertTrue(message = "Source and destination accounts must be distinct")
    public boolean isAccountsDistinct() {
        return sourceAccountId == null || destinationAccountId == null || !sourceAccountId.equals(destinationAccountId);
    }

    @JsonAnySetter
    public void rejectUnknownField(String field, Object value) { throw new IllegalArgumentException("Unknown transfer field"); }
}
