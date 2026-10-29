package com.bankops.banking.transfer;

import com.bankops.banking.transfer.dto.CreateTransferRequest;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.sql.SQLException;
import java.util.HexFormat;
import org.springframework.dao.DataAccessException;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@org.springframework.security.access.prepost.PreAuthorize("hasRole('OPERATOR')")
public class TransferService {
    public static final String IDEMPOTENCY_SCOPE = "POST:/api/v1/transfers";
    public static final String FUNDING_SCOPE = "POST:/api/v1/dev/accounts/fund";
    private static final BigDecimal MAX_BALANCE = new BigDecimal("99999999999999999.99");
    public record Result(Transfer transfer, boolean executed) {}
    private final TransferRepository repository;
    private final com.bankops.banking.customer.CustomerRepository customers;
    public TransferService(TransferRepository repository,com.bankops.banking.customer.CustomerRepository customers) { this.repository = repository;this.customers=customers; }

    @Transactional(readOnly = true)
    public Transfer get(java.util.UUID id) {
        return repository.findById(id).orElseThrow(() -> new TransferRequestException(
            HttpStatus.NOT_FOUND, "TRANSFER_NOT_FOUND", "Transfer not found"));
    }

    @Transactional
    public Result create(String key, CreateTransferRequest request) {
        return execute(IDEMPOTENCY_SCOPE, key, request);
    }

    @Transactional
    public Result fund(String key, java.util.UUID source, java.util.UUID destination, BigDecimal amount) {
        return execute(FUNDING_SCOPE, key, new CreateTransferRequest(source, destination, amount));
    }

    private Result execute(String scope, String key, CreateTransferRequest request) {
        return execute(scope,key,request,null);
    }
    @Transactional
    @org.springframework.security.access.prepost.PreAuthorize("hasRole('CUSTOMER')")
    public Result createCustomer(String key,CreateTransferRequest request) {
        var id=com.bankops.banking.customer.CustomerPrincipal.current().id();
        return execute("POST:/customer/transfers/"+id,key,request,id);
    }
    @Transactional(readOnly=true)
    @org.springframework.security.access.prepost.PreAuthorize("hasRole('CUSTOMER')")
    public Transfer getCustomer(java.util.UUID id) {
        var owner=com.bankops.banking.customer.CustomerPrincipal.current().id();
        return repository.findById(id).filter(t->customers.owns(t.sourceAccountId(),owner)).orElseThrow(()->new TransferRequestException(
            HttpStatus.NOT_FOUND,"TRANSFER_NOT_FOUND","Transfer not found"));
    }
    private Result execute(String scope, String key, CreateTransferRequest request,java.util.UUID customer) {
        if (key == null || key.isBlank() || key.length() > 255) {
            throw new TransferRequestException(HttpStatus.BAD_REQUEST, "INVALID_IDEMPOTENCY_KEY", "Idempotency-Key must contain 1 to 255 nonblank characters");
        }
        var accounts = repository.lockAccounts(request.sourceAccountId(), request.destinationAccountId());
        if(customer!=null && (!customers.owns(request.sourceAccountId(),customer)||!customers.hasOwner(request.destinationAccountId())))
            throw new TransferRequestException(HttpStatus.NOT_FOUND,"ACCOUNT_NOT_FOUND","Account not found");
        if (accounts.size() != 2) {
            throw new TransferRequestException(HttpStatus.NOT_FOUND, "ACCOUNT_NOT_FOUND", "Source or destination account not found");
        }
        var amount = request.amount().setScale(2);
        java.util.UUID id;
        try {
            id = repository.claim(scope, key, fingerprint(request, amount), request.sourceAccountId(), request.destinationAccountId(), amount);
        } catch (DataAccessException error) {
            // Inputs are already validated. V5's 23514 in this operation indicates
            // a conflicting fingerprint or immutable transfer request details.
            if (hasSqlState(error, "23514")) {
                throw new TransferRequestException(HttpStatus.CONFLICT, "IDEMPOTENCY_CONFLICT", "Idempotency-Key was already used for a different request");
            }
            throw error;
        }
        var transfer = repository.lockTransfer(id);
        if (!transfer.status().equals("PENDING")) return new Result(transfer, false);

        int postings = repository.postingCount(id);
        if (postings == 0) {
            var source = accounts.stream().filter(a -> a.id().equals(request.sourceAccountId())).findFirst().orElseThrow();
            var destination = accounts.stream().filter(a -> a.id().equals(request.destinationAccountId())).findFirst().orElseThrow();
            if (source.balance().compareTo(amount) < 0) {
                throw new TransferRequestException(HttpStatus.UNPROCESSABLE_CONTENT, "INSUFFICIENT_FUNDS", "Source account has insufficient funds");
            }
            if (destination.balance().add(amount).compareTo(MAX_BALANCE) > 0) {
                throw new TransferRequestException(HttpStatus.UNPROCESSABLE_CONTENT, "BALANCE_LIMIT_EXCEEDED", "Destination balance limit would be exceeded");
            }
            repository.post(transfer);
        } else if (postings != 2) {
            throw new IllegalStateException("Pending transfer has invalid postings");
        }
        // Existing balanced PENDING postings (allowed by V2) are completed without reposting.
        repository.complete(id);
        return new Result(repository.lockTransfer(id), true);
    }
    private String fingerprint(CreateTransferRequest request, BigDecimal amount) {
        String canonical = "v1|USD|" + request.sourceAccountId() + "|" + request.destinationAccountId() + "|" + amount.toPlainString();
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(canonical.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException impossible) { throw new IllegalStateException("SHA-256 unavailable", impossible); }
    }
    private boolean hasSqlState(Throwable error, String state) {
        for (Throwable cause = error; cause != null; cause = cause.getCause()) {
            if (cause instanceof SQLException sql && state.equals(sql.getSQLState())) return true;
        }
        return false;
    }
}
