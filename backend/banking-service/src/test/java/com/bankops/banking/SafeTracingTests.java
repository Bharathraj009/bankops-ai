package com.bankops.banking;

import com.bankops.banking.observability.SafeTracing;
import io.opentelemetry.api.OpenTelemetry;
import io.opentelemetry.api.trace.*;
import io.opentelemetry.context.Context;
import io.opentelemetry.sdk.OpenTelemetrySdk;
import io.opentelemetry.sdk.trace.SdkTracerProvider;
import org.junit.jupiter.api.Test;
import org.slf4j.MDC;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class SafeTracingTests {
    @Test void errorRedispatchKeepsOriginalRequestTraceAndCleansThreadState() throws Exception {
        try(var telemetry=OpenTelemetrySdk.builder().setTracerProvider(SdkTracerProvider.builder().build()).build()) {
            var filter=new com.bankops.banking.observability.TracingFilter(telemetry,new SafeTracing(telemetry));
            var request=new org.springframework.mock.web.MockHttpServletRequest();
            var response=new org.springframework.mock.web.MockHttpServletResponse();
            String[] ids=new String[2];
            filter.doFilter(request,response,(req,res) -> {ids[0]=MDC.get("trace_id");ids[1]=MDC.get("span_id");});
            assertNotNull(ids[0]);assertNull(MDC.get("trace_id"));
            request.setDispatcherType(jakarta.servlet.DispatcherType.ERROR);
            request.setAttribute(jakarta.servlet.RequestDispatcher.ERROR_REQUEST_URI,"/PRIVATE_PATH");
            filter.doFilter(request,response,(req,res) -> {
                assertEquals(ids[0],MDC.get("trace_id"));assertEquals(ids[1],MDC.get("span_id"));
            });
            assertNull(MDC.get("trace_id"));assertNull(MDC.get("span_id"));
        }
    }
    @Test void nestedScopesRestoreTraceContextAndMdc() {
        try(var telemetry=OpenTelemetrySdk.builder().setTracerProvider(SdkTracerProvider.builder().build()).build()) {
            var tracing=new SafeTracing(telemetry);Context original=Context.current();
            assertNull(MDC.get("trace_id"));assertNull(MDC.get("span_id"));
            try(var server=tracing.open("http.request",SpanKind.SERVER,Context.root())) {
                String trace=MDC.get("trace_id"),span=MDC.get("span_id");
                assertTrue(trace.matches("[0-9a-f]{32}"));assertTrue(span.matches("[0-9a-f]{16}"));
                try(var child=tracing.open("db.call",SpanKind.CLIENT,Context.current())) {
                    assertEquals(trace,MDC.get("trace_id"));assertNotEquals(span,MDC.get("span_id"));
                    assertEquals(MDC.get("span_id"),Span.current().getSpanContext().getSpanId());
                }
                assertEquals(span,MDC.get("span_id"));assertEquals(span,Span.current().getSpanContext().getSpanId());
            }
            assertSame(original,Context.current());assertNull(MDC.get("trace_id"));assertNull(MDC.get("span_id"));
        }
    }
    @Test void setupFailuresRestorePreviousDiagnosticContext() {
        var telemetry=mock(OpenTelemetry.class);
        when(telemetry.getTracer(anyString())).thenThrow(new IllegalStateException("Tracing failed"));
        MDC.put("trace_id","a".repeat(32));MDC.put("span_id","b".repeat(16));
        Context original=Context.current();
        try(var ignored=new SafeTracing(telemetry).open("transfer.create",SpanKind.INTERNAL,original)) {
            assertEquals("a".repeat(32),MDC.get("trace_id"));assertEquals("b".repeat(16),MDC.get("span_id"));
            assertSame(original,Context.current());
        } finally {MDC.remove("trace_id");MDC.remove("span_id");}
    }
}
