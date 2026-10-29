package com.bankops.banking.monitoring;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Bean;
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.Tag;
import io.micrometer.core.instrument.config.MeterFilter;
import java.util.List;
import java.util.Set;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class MetricsConfiguration implements WebMvcConfigurer {
    private final TransferOutcomeMetrics outcomes;
    public MetricsConfiguration(TransferOutcomeMetrics outcomes) { this.outcomes=outcomes; }
    @Bean
    public static MeterFilter boundedHttpLabels() {
        Set<String> routes=Set.of("/api/v1/accounts","/api/v1/accounts/{accountId}",
            "/api/v1/accounts/{accountId}/transactions","/api/v1/transfers","/api/v1/transfers/{transferId}",
            "/api/v1/dev/accounts/{accountId}/fund","/actuator/health","/actuator/prometheus",
            "NOT_FOUND","UNKNOWN","REDIRECTION","root");
        Set<String> methods=Set.of("GET","POST","PUT","PATCH","DELETE","HEAD","OPTIONS","TRACE");
        Set<String> outcomes=Set.of("INFORMATIONAL","SUCCESS","REDIRECTION","CLIENT_ERROR","SERVER_ERROR","UNKNOWN");
        return new MeterFilter() {
            @Override public Meter.Id map(Meter.Id id) {
                if (!"http.server.requests".equals(id.getName())) return id;
                String uri=value(id,"uri"), method=value(id,"method"), status=value(id,"status"), outcome=value(id,"outcome");
                // Drop exception/error and arbitrary common tags; never accept raw paths.
                return id.replaceTags(List.of(Tag.of("uri",routes.contains(uri)?uri:"OTHER"),
                    Tag.of("method",methods.contains(method)?method:"OTHER"),
                    Tag.of("status",status.matches("[1-5][0-9]{2}")?status:"OTHER"),
                    Tag.of("outcome",outcomes.contains(outcome)?outcome:"UNKNOWN")));
            }
            private String value(Meter.Id id,String key) {
                String value=id.getTag(key); return value==null?"UNKNOWN":value;
            }
        };
    }
    @Override public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(outcomes).addPathPatterns("/api/v1/transfers","/api/v1/dev/accounts/*/fund");
    }
}
