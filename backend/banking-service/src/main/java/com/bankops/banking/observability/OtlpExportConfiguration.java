package com.bankops.banking.observability;

import io.opentelemetry.exporter.otlp.http.trace.OtlpHttpSpanExporter;
import io.opentelemetry.sdk.common.CompletableResultCode;
import io.opentelemetry.sdk.trace.data.SpanData;
import io.opentelemetry.sdk.trace.export.*;
import java.time.Duration;
import java.util.Collection;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.*;

@Configuration(proxyBeanMethods=false)
@ConditionalOnProperty(name="bankops.tracing.otlp.enabled",havingValue="true")
public class OtlpExportConfiguration {
    @Bean
    BatchSpanProcessor otlpSpanProcessor(
        @Value("${bankops.tracing.otlp.endpoint:http://localhost:4318/v1/traces}") String endpoint) {
        var exporter=OtlpHttpSpanExporter.builder().setEndpoint(endpoint).setTimeout(Duration.ofSeconds(2)).build();
        return BatchSpanProcessor.builder(new GuardedExporter(exporter)).setMaxQueueSize(1024)
            .setMaxExportBatchSize(128).setScheduleDelay(Duration.ofSeconds(1))
            .setExporterTimeout(Duration.ofSeconds(3)).build();
    }

    // Runs only on the SDK batch worker; a full queue drops telemetry instead of blocking banking work.
    private record GuardedExporter(SpanExporter delegate) implements SpanExporter {
        @Override public CompletableResultCode export(Collection<SpanData> spans) {
            try {return delegate.export(spans);} catch(RuntimeException ignored) {return CompletableResultCode.ofFailure();}
        }
        @Override public CompletableResultCode flush() {
            try {return delegate.flush();} catch(RuntimeException ignored) {return CompletableResultCode.ofFailure();}
        }
        @Override public CompletableResultCode shutdown() {
            try {return delegate.shutdown();} catch(RuntimeException ignored) {return CompletableResultCode.ofFailure();}
        }
    }
}
