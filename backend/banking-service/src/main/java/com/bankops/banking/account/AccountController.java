package com.bankops.banking.account;

import com.bankops.banking.account.dto.AccountResponse;
import com.bankops.banking.account.dto.CreateAccountRequest;
import com.bankops.banking.account.dto.AccountTransactionPage;
import jakarta.validation.Valid;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/accounts")
public class AccountController {
    private final AccountService service;

    public AccountController(AccountService service) { this.service = service; }

    @GetMapping("/{accountId}/transactions")
    public ResponseEntity<AccountTransactionPage> transactions(@PathVariable UUID accountId,
        @RequestParam(defaultValue = "0") int page, @RequestParam(defaultValue = "20") int size) {
        return ResponseEntity.ok(service.transactions(accountId, page, size));
    }

    @GetMapping("/{accountId}")
    public ResponseEntity<AccountResponse> get(@PathVariable UUID accountId) {
        return ResponseEntity.ok(AccountResponse.from(service.get(accountId)));
    }

    @PostMapping
    public ResponseEntity<AccountResponse> create(@Valid @RequestBody CreateAccountRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED).body(AccountResponse.from(service.create(request)));
    }
}
