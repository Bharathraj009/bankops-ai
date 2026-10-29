package com.bankops.banking.customer;

import java.util.UUID;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.context.SecurityContextHolder;

public record CustomerPrincipal(UUID id, String username) {
    @Override public String toString() {return "CustomerPrincipal[REDACTED]";}
    public static CustomerPrincipal current() {
        var auth = SecurityContextHolder.getContext().getAuthentication();
        if (auth == null || !auth.isAuthenticated() || !(auth.getPrincipal() instanceof CustomerPrincipal customer)
            || auth.getAuthorities().stream().noneMatch(a -> a.getAuthority().equals("ROLE_CUSTOMER")))
            throw new AccessDeniedException("Customer authentication required");
        return customer;
    }
}
