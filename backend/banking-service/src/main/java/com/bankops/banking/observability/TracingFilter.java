package com.bankops.banking.observability;

import io.opentelemetry.api.OpenTelemetry;
import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.context.Context;
import io.opentelemetry.context.propagation.TextMapGetter;
import jakarta.servlet.*;
import jakarta.servlet.http.*;
import java.io.IOException;
import java.util.*;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class TracingFilter extends OncePerRequestFilter {
    private static final String REQUEST_CONTEXT=TracingFilter.class.getName()+".context";
    private final OpenTelemetry telemetry;
    private final SafeTracing tracing;
    public TracingFilter(OpenTelemetry telemetry,SafeTracing tracing) {this.telemetry=telemetry;this.tracing=tracing;}
    private static final TextMapGetter<HttpServletRequest> HEADERS=new TextMapGetter<>() {
        @Override public Iterable<String> keys(HttpServletRequest request) {return List.of("traceparent");}
        @Override public String get(HttpServletRequest request,String key) {
            // No baggage or vendor tracestate: these may contain customer data.
            if(!"traceparent".equalsIgnoreCase(key)) return null;
            var values=Collections.list(request.getHeaders("traceparent"));
            return values.size()==1 && values.getFirst().length()<=512 ? values.getFirst():null;
        }
    };
    @Override protected boolean shouldNotFilterErrorDispatch() {return false;}
    @Override protected void doFilterInternal(HttpServletRequest request,HttpServletResponse response,FilterChain chain)
        throws ServletException,IOException {
        SafeTracing.TraceScope span=null;
        try {
            var existing=(Context)request.getAttribute(REQUEST_CONTEXT);
            if(existing!=null) span=tracing.resume(existing);
            else {
                Context parent=telemetry.getPropagators().getTextMapPropagator().extract(Context.root(),request,HEADERS);
                span=tracing.open("http.request",SpanKind.SERVER,parent);
                request.setAttribute(REQUEST_CONTEXT,Context.current());
            }
            telemetry.getPropagators().getTextMapPropagator().inject(Context.current(),response,
                (carrier,key,value) -> {if("traceparent".equals(key)) carrier.setHeader(key,value);});
        } catch(RuntimeException ignored) { /* Execute the request exactly once, even if tracing fails. */ }
        boolean completed=false;
        try {chain.doFilter(request,response);completed=true;}
        finally {if(span!=null) {span.status(completed?response.getStatus():500);span.close();}}
    }
}
