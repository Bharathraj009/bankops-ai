package com.bankops.banking.customer;

import com.bankops.banking.account.dto.CreateAccountRequest;
import com.bankops.banking.transfer.Transfer;
import com.bankops.banking.transfer.TransferService;
import com.bankops.banking.transfer.dto.CreateTransferRequest;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.UUID;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/customer")
public class CustomerController {
    public record AccountCreate(@jakarta.validation.constraints.Pattern(regexp="USD") String currency) {
        public AccountCreate {if(currency==null)currency="USD";}
        @com.fasterxml.jackson.annotation.JsonAnySetter public void unknown(String name,Object value) {throw new IllegalArgumentException("Unsupported field");}
    }
    public record TransferView(UUID id,UUID sourceAccountId,BigDecimal amount,String currency,String status,OffsetDateTime createdAt) {
        static TransferView from(Transfer t) {return new TransferView(t.id(),t.sourceAccountId(),t.amount(),t.currency(),t.status(),t.createdAt());}
    }
    private final CustomerAuthService auth;
    private final CustomerBankingService banking;
    private final CustomerRepository customers;
    private final TransferService transfers;
    public CustomerController(CustomerAuthService auth,CustomerBankingService banking,CustomerRepository customers,TransferService transfers) {
        this.auth=auth;this.banking=banking;this.customers=customers;this.transfers=transfers;
    }
    @PostMapping("/register") public ResponseEntity<CustomerPrincipal> register(@Valid @RequestBody CustomerAuthService.Credentials body,HttpServletRequest request) {
        auth.attempt(request.getRemoteAddr());return ResponseEntity.status(201).body(auth.register(body));
    }
    @PostMapping("/login") public CustomerAuthService.Session login(@Valid @RequestBody CustomerAuthService.Credentials body,HttpServletRequest request) {
        auth.attempt(request.getRemoteAddr());return auth.login(body);
    }
    @GetMapping("/me") public CustomerPrincipal me() {return CustomerPrincipal.current();}
    @PostMapping("/logout") public ResponseEntity<Void> logout(@RequestHeader("Authorization") String token) {
        CustomerPrincipal.current();customers.revoke(token.substring(7));return ResponseEntity.noContent().build();
    }
    @GetMapping("/accounts") public CustomerBankingService.Accounts accounts(@RequestParam(defaultValue="0") int page,@RequestParam(defaultValue="20") int size) {return banking.list(page,size);}
    @PostMapping("/accounts") public ResponseEntity<?> create(@Valid @RequestBody AccountCreate body) {
        return ResponseEntity.status(201).body(banking.create(new CreateAccountRequest("CUS-"+UUID.randomUUID(),body.currency())));
    }
    @GetMapping("/accounts/{id}") public Object account(@PathVariable UUID id) {return banking.get(id);}
    @GetMapping("/accounts/{id}/transactions") public Object history(@PathVariable UUID id,@RequestParam(defaultValue="0") int page,@RequestParam(defaultValue="20") int size) {return banking.history(id,page,size);}
    @PostMapping("/transfers") public ResponseEntity<TransferView> transfer(@RequestHeader("Idempotency-Key") String key,@Valid @RequestBody CreateTransferRequest body) {
        var result=transfers.createCustomer(key,body);return ResponseEntity.status(result.executed()?201:200).body(TransferView.from(result.transfer()));
    }
    @GetMapping("/transfers/{id}") public TransferView transfer(@PathVariable UUID id) {return TransferView.from(transfers.getCustomer(id));}
}
