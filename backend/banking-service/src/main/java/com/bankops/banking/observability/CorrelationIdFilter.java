package com.bankops.banking.observability;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.Collections;
import java.util.UUID;
import org.slf4j.MDC;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE+10)
public class CorrelationIdFilter extends OncePerRequestFilter {
    public static final String HEADER = "X-Correlation-ID";
    private static final String ATTRIBUTE = CorrelationIdFilter.class.getName()+".id";
    private final SafeEventLogger events;

    public CorrelationIdFilter(SafeEventLogger events) { this.events = events; }

    @Override protected boolean shouldNotFilterAsyncDispatch() { return false; }
    @Override protected boolean shouldNotFilterErrorDispatch() { return false; }

    @Override protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                            FilterChain chain) throws ServletException, IOException {
        String id = (String) request.getAttribute(ATTRIBUTE);
        if (id == null) {
            var headers = Collections.list(request.getHeaders(HEADER));
            // Accept only a single opaque UUID, never arbitrary user text or log-injection payloads.
            id = headers.size() == 1 && headers.getFirst().matches(
                "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
                ? headers.getFirst().toLowerCase(java.util.Locale.ROOT) : UUID.randomUUID().toString();
            request.setAttribute(ATTRIBUTE, id);
        }
        response.setHeader(HEADER, id);
        String previous = null;
        try { previous = MDC.get("correlation_id"); MDC.put("correlation_id", id); }
        catch (RuntimeException ignored) { /* Diagnostic failures cannot block requests. */ }
        boolean completed = false;
        try {
            chain.doFilter(request, response);
            completed = true;
        } finally {
            try { events.requestCompleted(completed ? response.getStatus() : 500); }
            catch (RuntimeException ignored) { /* Never mask a response or transaction result. */ }
            try {
                if (previous == null) MDC.remove("correlation_id"); else MDC.put("correlation_id", previous);
            } catch (RuntimeException ignored) { /* Best-effort diagnostic cleanup. */ }
        }
    }
}
