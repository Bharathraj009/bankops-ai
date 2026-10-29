package com.bankops.banking.dev;

import com.fasterxml.jackson.annotation.JsonAnySetter;
import jakarta.validation.constraints.*;
import java.math.BigDecimal;

public record FundingRequest(@NotNull @DecimalMin(value="0", inclusive=false)
    @Digits(integer=17, fraction=2) BigDecimal amount) {
    @JsonAnySetter
    public void rejectUnknownField(String field, Object value) { throw new IllegalArgumentException("Unknown funding field"); }
}
