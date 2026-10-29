package com.bankops.banking.account;

import com.bankops.banking.account.dto.CreateAccountRequest;
import com.bankops.banking.account.dto.AccountTransactionPage;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.annotation.Isolation;

@Service
@org.springframework.security.access.prepost.PreAuthorize("hasRole('OPERATOR')")
public class AccountService {
    private final AccountRepository repository;

    public AccountService(AccountRepository repository) { this.repository = repository; }

    @Transactional(readOnly = true, isolation = Isolation.REPEATABLE_READ)
    public AccountTransactionPage transactions(UUID id, int page, int size) {
        if (page < 0 || size < 1 || size > 100) throw new InvalidPaginationException();
        repository.findById(id).orElseThrow(AccountNotFoundException::new);
        long total = repository.transactionCount(id);
        var entries = repository.transactions(id, size, (long) page * size);
        return new AccountTransactionPage(entries, page, size, total, total / size + (total % size == 0 ? 0 : 1));
    }

    @Transactional(readOnly = true)
    public Account get(UUID id) {
        return repository.findById(id).orElseThrow(AccountNotFoundException::new);
    }

    @Transactional
    public Account create(CreateAccountRequest request) {
        return repository.create(UUID.randomUUID(), request.accountNumber(), request.currency());
    }
}
