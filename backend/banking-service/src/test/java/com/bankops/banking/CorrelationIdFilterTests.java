package com.bankops.banking;

import com.bankops.banking.observability.CorrelationIdFilter;
import com.bankops.banking.observability.SafeEventLogger;
import jakarta.servlet.ServletException;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.slf4j.MDC;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class CorrelationIdFilterTests {
    @Test void cleansMdcWhenChainThrowsAndLoggingFails() throws Exception {
        var events=mock(SafeEventLogger.class);
        doThrow(new IllegalStateException("logger failed")).when(events).requestCompleted(anyInt());
        var filter=new CorrelationIdFilter(events);
        var request=new MockHttpServletRequest();var response=new MockHttpServletResponse();
        var original=new ServletException("original failure");
        assertNull(MDC.get("correlation_id"));
        assertSame(original,assertThrows(ServletException.class,() -> filter.doFilter(request,response,(req,res) -> {
            assertEquals(response.getHeader("X-Correlation-ID"),MDC.get("correlation_id"));
            throw original;
        })));
        assertNull(MDC.get("correlation_id"));verify(events).requestCompleted(500);
    }
    @Test void restoresPreviousContextAndNeverInvokesRequestTwiceOnLoggerFailure() throws Exception {
        var events=mock(SafeEventLogger.class);
        doThrow(new IllegalStateException("logger failed")).when(events).requestCompleted(anyInt());
        String previous=UUID.randomUUID().toString();MDC.put("correlation_id",previous);
        try {
            var response=new MockHttpServletResponse();var count=new java.util.concurrent.atomic.AtomicInteger();
            new CorrelationIdFilter(events).doFilter(new MockHttpServletRequest(),response,(req,res) -> {
                count.incrementAndGet();assertNotEquals(previous,MDC.get("correlation_id"));
            });
            assertEquals(1,count.get());assertEquals(previous,MDC.get("correlation_id"));
        } finally {MDC.remove("correlation_id");}
    }
}
