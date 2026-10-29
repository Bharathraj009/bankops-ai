package com.bankops.banking.dev;

import com.bankops.banking.account.AccountNotFoundException;
import com.bankops.banking.account.AccountService;
import com.bankops.banking.transfer.TransferRequestException;
import com.bankops.banking.transfer.TransferService;
import java.math.BigDecimal;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

@Service
@Profile("dev & !prod & !production & !test")
public class DevFundingService {
    private final TransferService transfers;
    private final AccountService accounts;
    private final String fundingAccount;
    public DevFundingService(TransferService transfers, AccountService accounts,
        @Value("${bankops.dev.funding-account-id:}") String fundingAccount) {
        this.transfers=transfers; this.accounts=accounts; this.fundingAccount=fundingAccount;
    }
    public TransferService.Result fund(UUID target, String key, BigDecimal amount) {
        UUID source;
        try { source=UUID.fromString(fundingAccount); }
        catch (IllegalArgumentException error) { throw unavailable(); }
        if (source.equals(target)) throw new TransferRequestException(HttpStatus.BAD_REQUEST,
            "INVALID_FUNDING_TARGET", "The system funding account cannot fund itself");
        try { accounts.get(source); }
        catch (AccountNotFoundException error) { throw unavailable(); }
        return transfers.fund(key, source, target, amount);
    }
    private TransferRequestException unavailable() {
        return new TransferRequestException(HttpStatus.SERVICE_UNAVAILABLE,
            "FUNDING_UNAVAILABLE", "Development funding account is not configured or available");
    }
}
