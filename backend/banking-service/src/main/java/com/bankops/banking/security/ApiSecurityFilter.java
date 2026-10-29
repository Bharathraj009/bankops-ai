package com.bankops.banking.security;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.Collections;
import java.util.Locale;
import java.util.Set;
import java.util.stream.Collectors;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

/** Deployment boundary only; never changes financial validation or transactions. */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 15)
public class ApiSecurityFilter extends OncePerRequestFilter {
    private final String token;
    private final boolean required;
    private final Set<String> hosts;
    public ApiSecurityFilter(Environment environment,
        @Value("${BANKOPS_BANKING_API_TOKEN:}") String token,
        @Value("${BANKOPS_ALLOWED_HOSTS:localhost,127.0.0.1,::1}") String hosts,
        @Value("${server.address:127.0.0.1}") String address) {
        this.token = token;
        this.hosts = Arrays.stream(hosts.split(",")).map(s -> s.trim().toLowerCase(Locale.ROOT)).collect(Collectors.toSet());
        if (this.hosts.contains("*") || (!token.isEmpty() && (token.startsWith("cus_") || token.length() < 32 || token.length() > 256 || !token.matches("[!-~]+"))))
            throw new IllegalArgumentException("Invalid API security configuration");
        this.required = !token.isEmpty() || environment.matchesProfiles("prod", "production")
            || !Set.of("127.0.0.1", "localhost", "::1").contains(address);
    }
    @Override protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
        throws ServletException, IOException {
        response.setHeader("Cache-Control", "no-store");
        response.setHeader("X-Content-Type-Options", "nosniff");
        response.setHeader("X-Frame-Options", "DENY");
        response.setHeader("Referrer-Policy", "no-referrer");
        var hostHeaders = Collections.list(request.getHeaders("Host"));
        if (hostHeaders.size() > 1 || !hosts.contains(request.getServerName().replace("[", "").replace("]", "").toLowerCase(Locale.ROOT))) {
            deny(response, 403); return;
        }
        var origins = Collections.list(request.getHeaders("Origin"));
        if ("cross-site".equals(request.getHeader("Sec-Fetch-Site")) || origins.size() > 1) { deny(response, 403); return; }
        if (!origins.isEmpty()) {
            try {
                var origin = URI.create(origins.getFirst());
                String host = request.getHeader("Host");
                if (!("http".equals(origin.getScheme()) || "https".equals(origin.getScheme())) || origin.getRawUserInfo() != null
                    || origin.getRawQuery() != null || origin.getRawFragment() != null || !"".equals(origin.getRawPath())
                    || host == null || !host.equalsIgnoreCase(origin.getRawAuthority())) { deny(response, 403); return; }
            } catch (IllegalArgumentException error) { deny(response, 403); return; }
        }
        String path = request.getRequestURI().substring(request.getContextPath().length());
        boolean publicHealth = "GET".equals(request.getMethod()) && path.equals("/actuator/health");
        // Authenticate before routing, including context paths and path parameters.
        // A route allowlist here could be bypassed by servlet path normalization.
        boolean customerRoute=path.startsWith("/api/v1/customer/");
        if ((required || path.startsWith("/api/v1/")) && !publicHealth && !customerRoute) {
            if (token.isEmpty()) { deny(response, 503); return; }
            var headers = Collections.list(request.getHeaders("Authorization"));
            if (headers.size() != 1 || headers.getFirst().length() > 300 || !MessageDigest.isEqual(
                ("Bearer " + token).getBytes(StandardCharsets.UTF_8), headers.getFirst().getBytes(StandardCharsets.UTF_8))) {
                response.setHeader("WWW-Authenticate", "Bearer"); deny(response, 401); return;
            }
        }
        chain.doFilter(request, response);
    }
    private void deny(HttpServletResponse response, int status) throws IOException {
        response.setStatus(status); response.setContentType("application/json");
        response.getWriter().write("{\"error\":\"Request unavailable\"}");
    }
}
