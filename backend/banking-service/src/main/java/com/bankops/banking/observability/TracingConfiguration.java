package com.bankops.banking.observability;

import io.opentelemetry.api.common.Attributes;
import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.context.propagation.ContextPropagators;
import io.opentelemetry.api.trace.propagation.W3CTraceContextPropagator;
import io.opentelemetry.sdk.OpenTelemetrySdk;
import io.opentelemetry.sdk.resources.Resource;
import io.opentelemetry.sdk.trace.*;
import io.opentelemetry.sdk.common.CompletableResultCode;
import io.opentelemetry.context.Context;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.context.annotation.*;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass=true)
public class TracingConfiguration {
    @Bean(destroyMethod="close")
    OpenTelemetrySdk bankopsOpenTelemetry(ObjectProvider<SpanProcessor> processors) {
        var builder=SdkTracerProvider.builder().setSampler(io.opentelemetry.sdk.trace.samplers.Sampler.parentBased(
            io.opentelemetry.sdk.trace.samplers.Sampler.alwaysOn())).setResource(Resource.create(Attributes.of(
            AttributeKey.stringKey("service.name"),"banking-service")));
        processors.orderedStream().forEach(p -> builder.addSpanProcessor(new GuardedProcessor(p)));
        return OpenTelemetrySdk.builder().setTracerProvider(builder.build())
            .setPropagators(ContextPropagators.create(W3CTraceContextPropagator.getInstance())).build();
    }

    /** Isolate processor/exporter runtime failures, including start and shutdown hooks. */
    private record GuardedProcessor(SpanProcessor delegate) implements SpanProcessor {
        @Override public void onStart(Context parent,ReadWriteSpan span) {
            try {delegate.onStart(parent,span);} catch(RuntimeException ignored) { }
        }
        @Override public boolean isStartRequired() {return true;}
        @Override public void onEnd(ReadableSpan span) {
            try {delegate.onEnd(span);} catch(RuntimeException ignored) { }
        }
        @Override public boolean isEndRequired() {return true;}
        @Override public CompletableResultCode shutdown() {
            try {return delegate.shutdown();} catch(RuntimeException ignored) {return CompletableResultCode.ofFailure();}
        }
        @Override public CompletableResultCode forceFlush() {
            try {return delegate.forceFlush();} catch(RuntimeException ignored) {return CompletableResultCode.ofFailure();}
        }
    }
}
