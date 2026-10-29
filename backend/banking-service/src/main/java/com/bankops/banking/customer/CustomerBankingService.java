package com.bankops.banking.customer;

import com.bankops.banking.account.*;
import com.bankops.banking.account.dto.*;
import java.util.List;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Service
@PreAuthorize("hasRole('CUSTOMER')")
public class CustomerBankingService {
    public record Accounts(List<AccountResponse> accounts,int page,int size,long totalElements,long totalPages) {}
    private final CustomerRepository customers;
    private final AccountRepository accounts;
    private final JdbcTemplate jdbc;
    public CustomerBankingService(CustomerRepository customers,AccountRepository accounts,JdbcTemplate jdbc) {this.customers=customers;this.accounts=accounts;this.jdbc=jdbc;}
    private UUID owner() {return CustomerPrincipal.current().id();}
    private void check(UUID account) {if(!customers.owns(account,owner()))throw new AccountNotFoundException();}
    private void pagination(int page,int size) {if(page<0||size<1||size>100)throw new InvalidPaginationException();}
    @Transactional public AccountResponse create(CreateAccountRequest request) {
        UUID customer=owner();var account=accounts.create(UUID.randomUUID(),request.accountNumber(),request.currency());
        customers.assignNew(account.id(),customer);return AccountResponse.from(account);
    }
    @Transactional(readOnly=true) public AccountResponse get(UUID id) {check(id);return AccountResponse.from(accounts.findById(id).orElseThrow(AccountNotFoundException::new));}
    @Transactional(readOnly=true,isolation=Isolation.REPEATABLE_READ) public Accounts list(int page,int size) {
        pagination(page,size);UUID customer=owner();
        long total=jdbc.queryForObject("SELECT count(*) FROM customer_account_ownership WHERE customer_id=?",Long.class,customer);
        var rows=jdbc.query("""
            SELECT a.id,a.account_number,a.currency,a.balance,a.created_at FROM accounts a
            JOIN customer_account_ownership o ON o.account_id=a.id WHERE o.customer_id=?
            ORDER BY a.created_at DESC,a.id DESC LIMIT ? OFFSET ?
            """,(r,n)->new AccountResponse(r.getObject("id",UUID.class),r.getString("account_number"),r.getString("currency"),
                r.getBigDecimal("balance"),r.getObject("created_at",java.time.OffsetDateTime.class)),customer,size,(long)page*size);
        return new Accounts(rows,page,size,total,total/size+(total%size==0?0:1));
    }
    @Transactional(readOnly=true,isolation=Isolation.REPEATABLE_READ) public AccountTransactionPage history(UUID id,int page,int size) {
        pagination(page,size);check(id);long total=accounts.transactionCount(id);
        return new AccountTransactionPage(accounts.transactions(id,size,(long)page*size),page,size,total,total/size+(total%size==0?0:1));
    }
}
