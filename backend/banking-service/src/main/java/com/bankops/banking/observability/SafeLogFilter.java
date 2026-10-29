package com.bankops.banking.observability;

import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.filter.Filter;
import ch.qos.logback.core.spi.FilterReply;

/** A final allowlist prevents framework DEBUG/error output from disclosing requests or SQL. */
public class SafeLogFilter extends Filter<ILoggingEvent> {
    @Override public FilterReply decide(ILoggingEvent event) {
        if (!SafeEventLogger.class.getName().equals(event.getLoggerName())
            || event.getThrowableProxy() != null
            || !java.util.Set.of("HTTP request completed", "Transfer HTTP outcome").contains(event.getMessage())) {
            return FilterReply.DENY;
        }
        // Do not serialize arbitrary MDC values introduced by other libraries.
        for (var entry : event.getMDCPropertyMap().entrySet()) {
            String pattern=switch(entry.getKey()) {
                case "correlation_id" -> "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";
                case "trace_id" -> "[0-9a-f]{32}";
                case "span_id" -> "[0-9a-f]{16}";
                default -> null;
            };
            if(pattern==null || !entry.getValue().matches(pattern)) return FilterReply.DENY;
        }
        var fields = event.getKeyValuePairs();
        if (fields == null || fields.isEmpty()) return FilterReply.DENY;
        for (var field : fields) {
            boolean valid = switch (field.key) {
                case "event_type" -> java.util.Set.of("http_request_completed", "transfer_outcome").contains(String.valueOf(field.value));
                case "operation" -> java.util.Set.of("transfer", "dev_funding").contains(String.valueOf(field.value));
                case "outcome" -> java.util.Set.of("completed", "replayed", "invalid_request", "account_not_found",
                    "idempotency_conflict", "rejected", "server_error", "other").contains(String.valueOf(field.value));
                case "http_status" -> field.value instanceof Integer status && status >= 100 && status <= 599;
                default -> false;
            };
            if (!valid) return FilterReply.DENY;
        }
        return FilterReply.NEUTRAL;
    }
}
