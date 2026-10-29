package com.bankops.banking.monitoring;

import io.micrometer.core.instrument.MeterRegistry;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.HandlerMapping;

/** Observes HTTP results after transactional services return; never participates in money movement. */
@Component
public class TransferOutcomeMetrics implements HandlerInterceptor {
    private final MeterRegistry registry;
    private final com.bankops.banking.observability.SafeEventLogger events;
    public TransferOutcomeMetrics(MeterRegistry registry, com.bankops.banking.observability.SafeEventLogger events) {
        this.registry=registry;
        this.events=events;
    }

    @Override public void afterCompletion(HttpServletRequest request, HttpServletResponse response, Object handler, Exception exception) {
        if (!"POST".equals(request.getMethod())) return;
        Object route=request.getAttribute(HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);
        String operation;
        if ("/api/v1/transfers".equals(route)) operation="transfer";
        else if ("/api/v1/dev/accounts/{accountId}/fund".equals(route)) operation="dev_funding";
        else return;
        int status=response.getStatus();
        String outcome=switch(status) {
            case 201 -> "completed";
            case 200 -> "replayed";
            case 400 -> "invalid_request";
            case 404 -> "account_not_found";
            case 409 -> "idempotency_conflict";
            case 422 -> "rejected";
            default -> status>=500 ? "server_error" : "other";
        };
        try {
            registry.counter("bankops.transfer.outcomes","operation",operation,"outcome",outcome).increment();
        } catch (RuntimeException ignored) {
            // Monitoring is best effort. A registry failure must not affect HTTP or transactions.
        }
        try {
            events.transferOutcome(operation, outcome);
        } catch (RuntimeException ignored) {
            // Logging is independent of metrics and financial transaction results.
        }
    }
}
