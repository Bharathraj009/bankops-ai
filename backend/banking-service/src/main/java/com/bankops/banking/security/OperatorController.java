package com.bankops.banking.security;

import java.util.Map;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

@RestController
public class OperatorController {
    @GetMapping("/api/v1/operator/me")
    @PreAuthorize("hasRole('OPERATOR')")
    public Map<String,String> me() {return Map.of("role","OPERATOR");}
}
