package com.bankops.banking.observability;

import io.opentelemetry.api.OpenTelemetry;
import io.opentelemetry.api.trace.*;
import io.opentelemetry.context.*;
import org.slf4j.MDC;
import org.springframework.stereotype.Component;

/** No values from business arguments, return values, exceptions or SQL are accepted. */
@Component
public class SafeTracing {
    private final OpenTelemetry telemetry;
    public SafeTracing(OpenTelemetry telemetry) {this.telemetry=telemetry;}

    public TraceScope open(String name,SpanKind kind,Context parent) {
        var result=new TraceScope();
        try {
            if(!java.util.Set.of("http.request","transfer.create","transfer.read","transfer.fund","db.call").contains(name)) return result;
            result.previousTrace=MDC.get("trace_id");result.previousSpan=MDC.get("span_id");
            result.restoreMdc=true;
            result.span=telemetry.getTracer("bankops-banking").spanBuilder(name).setSpanKind(kind)
                .setParent(parent).startSpan();
            if("db.call".equals(name)) result.span.setAttribute("db.system.name","postgresql");
            result.scope=result.span.makeCurrent();
            var context=result.span.getSpanContext();
            MDC.put("trace_id",context.getTraceId());MDC.put("span_id",context.getSpanId());
        } catch(RuntimeException ignored) {result.close();}
        return result;
    }

    public TraceScope resume(Context context) {
        var result=new TraceScope();
        try {
            result.previousTrace=MDC.get("trace_id");result.previousSpan=MDC.get("span_id");result.restoreMdc=true;
            result.scope=context.makeCurrent();
            var span=Span.fromContext(context).getSpanContext();
            if(span.isValid()) {MDC.put("trace_id",span.getTraceId());MDC.put("span_id",span.getSpanId());}
        } catch(RuntimeException ignored) {result.close();}
        return result;
    }

    public static final class TraceScope implements AutoCloseable {
        private Span span;
        private Scope scope;
        private String previousTrace,previousSpan;
        private boolean restoreMdc,closed;
        public void status(int code) {
            try {if(span!=null) {span.setAttribute("http.response.status_code",code);if(code>=500) span.setStatus(StatusCode.ERROR);}}
            catch(RuntimeException ignored) { }
        }
        public void failed() {
            // Never recordException: database/validation messages may include confidential input.
            try {if(span!=null) span.setStatus(StatusCode.ERROR);} catch(RuntimeException ignored) { }
        }
        @Override public void close() {
            if(closed) return;
            closed=true;
            try {if(scope!=null) scope.close();} catch(RuntimeException ignored) { }
            try {
                if(restoreMdc) {
                    if(previousTrace==null) MDC.remove("trace_id");else MDC.put("trace_id",previousTrace);
                    if(previousSpan==null) MDC.remove("span_id");else MDC.put("span_id",previousSpan);
                }
            } catch(RuntimeException ignored) { }
            try {if(span!=null) span.end();} catch(RuntimeException ignored) { }
        }
    }
}
