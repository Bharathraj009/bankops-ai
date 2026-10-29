package com.bankops.banking.observability;

import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/** Only bounded outcome fields; never accepts request objects, identifiers or exceptions. */
@Component
public class SafeEventLogger {
    public void requestCompleted(int status) {
        LoggerFactory.getLogger(SafeEventLogger.class).atInfo()
            .addKeyValue("event_type", "http_request_completed")
            .addKeyValue("http_status", status).log("HTTP request completed");
    }

    public void transferOutcome(String operation, String outcome) {
        if (!java.util.Set.of("transfer", "dev_funding").contains(operation)
            || !java.util.Set.of("completed", "replayed", "invalid_request", "account_not_found",
                "idempotency_conflict", "rejected", "server_error", "other").contains(outcome)) return;
        LoggerFactory.getLogger(SafeEventLogger.class).atInfo()
            .addKeyValue("event_type", "transfer_outcome")
            .addKeyValue("operation", operation).addKeyValue("outcome", outcome)
            .log("Transfer HTTP outcome");
    }
}
