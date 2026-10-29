package com.bankops.banking.observability;

import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.context.Context;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.*;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Aspect
@Component
@Order(Ordered.LOWEST_PRECEDENCE-10)
public class TracingAspect {
    private final SafeTracing tracing;
    public TracingAspect(SafeTracing tracing) {this.tracing=tracing;}
    @Around("execution(public * com.bankops.banking.transfer.TransferService.*(..))")
    public Object transfer(ProceedingJoinPoint call) throws Throwable {
        String name=switch(call.getSignature().getName()) {
            case "create" -> "transfer.create";
            case "fund" -> "transfer.fund";
            case "get" -> "transfer.read";
            default -> null;
        };
        return trace(call,name);
    }
    @Around("execution(public * com.bankops.banking.account.AccountRepository.*(..)) || execution(public * com.bankops.banking.transfer.TransferRepository.*(..))")
    public Object database(ProceedingJoinPoint call) throws Throwable {return trace(call,"db.call");}
    private Object trace(ProceedingJoinPoint call,String name) throws Throwable {
        SafeTracing.TraceScope span=null;
        try {if(name!=null) span=tracing.open(name,"db.call".equals(name)?SpanKind.CLIENT:SpanKind.INTERNAL,Context.current());}
        catch(RuntimeException ignored) { }
        // The invocation is deliberately outside the tracing error handler: never retry business work.
        try {return call.proceed();}
        catch(Throwable failure) {if(span!=null) span.failed();throw failure;}
        finally {if(span!=null) span.close();}
    }
}
