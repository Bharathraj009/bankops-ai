package com.bankops.banking;
import com.bankops.banking.customer.CustomerAuthService;
import org.junit.jupiter.api.Test;
import org.springframework.web.server.ResponseStatusException;
import static org.junit.jupiter.api.Assertions.*;
class CustomerAuthLimitsTests {
    @Test void authenticationWorkIsBoundedAndPasswordByteLimitPreventsBcryptTruncation() {
        var limiter=new CustomerAuthService(null,null,null,null,2);
        limiter.attempt("127.0.0.1");limiter.attempt("127.0.0.1");
        assertEquals(429,assertThrows(ResponseStatusException.class,()->limiter.attempt("127.0.0.1")).getStatusCode().value());
        assertFalse(new CustomerAuthService.Credentials("customer","é".repeat(40)).isPasswordWithinLimit());
        assertTrue(new CustomerAuthService.Credentials("customer","safe-password-long").isPasswordWithinLimit());
    }
}
