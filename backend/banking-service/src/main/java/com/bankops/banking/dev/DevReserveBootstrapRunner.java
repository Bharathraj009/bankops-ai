package com.bankops.banking.dev;

import java.math.BigDecimal;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("dev & !prod & !production & !test")
@ConditionalOnProperty(name="bankops.dev.reserve-bootstrap.enabled",havingValue="true")
public class DevReserveBootstrapRunner implements ApplicationRunner {
    private final DevReserveBootstrap bootstrap;
    private final String account;
    private final BigDecimal initialBalance;
    public DevReserveBootstrapRunner(DevReserveBootstrap bootstrap,
        @Value("${bankops.dev.funding-account-id:}") String account,
        @Value("${bankops.dev.reserve-bootstrap.initial-balance:1000000.00}") BigDecimal initialBalance) {
        this.bootstrap=bootstrap; this.account=account; this.initialBalance=initialBalance;
    }
    @Override public void run(ApplicationArguments args) {
        bootstrap.initialize(UUID.fromString(account),initialBalance);
    }
}
