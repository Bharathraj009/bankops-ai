package com.bankops.banking;

import java.sql.DriverManager;
import java.util.UUID;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

/** Requires an explicitly selected test PostgreSQL; never uses application credentials. */
abstract class IsolatedPostgresTest {
    static final String OPERATOR_TOKEN="test_"+UUID.randomUUID()+UUID.randomUUID();
    static java.net.http.HttpRequest.Builder operatorRequest(java.net.URI uri) {
        return java.net.http.HttpRequest.newBuilder(uri).header("Authorization","Bearer "+OPERATOR_TOKEN);
    }
    static <T> T asOperator(java.util.concurrent.Callable<T> operation) throws Exception {
        var previous=org.springframework.security.core.context.SecurityContextHolder.getContext();
        var context=org.springframework.security.core.context.SecurityContextHolder.createEmptyContext();
        context.setAuthentication(org.springframework.security.authentication.UsernamePasswordAuthenticationToken.authenticated(
            "isolated-operator",null,java.util.List.of(new org.springframework.security.core.authority.SimpleGrantedAuthority("ROLE_OPERATOR"))));
        try {org.springframework.security.core.context.SecurityContextHolder.setContext(context);return operation.call();}
        finally {org.springframework.security.core.context.SecurityContextHolder.setContext(previous);}
    }
    private static final String SCHEMA = "test_" + UUID.randomUUID().toString().replace("-", "");

    @DynamicPropertySource
    static void postgres(DynamicPropertyRegistry registry) throws Exception {
        String url = required("BANKOPS_TEST_DB_URL");
        String user = required("BANKOPS_TEST_DB_USER");
        String password = required("BANKOPS_TEST_DB_PASSWORD");
        try (var c = DriverManager.getConnection(url, user, password);
             var s = c.createStatement()) {
            s.execute("CREATE SCHEMA IF NOT EXISTS " + SCHEMA);
        }
        registry.add("spring.datasource.url", () -> url);
        registry.add("spring.datasource.username", () -> user);
        registry.add("spring.datasource.password", () -> password);
        registry.add("spring.datasource.hikari.schema", () -> SCHEMA);
        registry.add("spring.datasource.hikari.maximum-pool-size", () -> 2);
        registry.add("spring.datasource.hikari.minimum-idle", () -> 1);
        registry.add("spring.flyway.default-schema", () -> SCHEMA);
        registry.add("spring.flyway.enabled", () -> true);
        // Legacy invariant fixtures deliberately exercise DDL/corruption using
        // an isolated administrator. Real runtime ACLs have a separate HTTP suite.
        registry.add("bankops.database.verify-runtime", () -> false);
        registry.add("spring.flyway.schemas", () -> SCHEMA);
        registry.add("BANKOPS_BANKING_API_TOKEN", () -> OPERATOR_TOKEN);
    }

    private static String required(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) throw new IllegalStateException(name + " must select an isolated test PostgreSQL instance");
        return value;
    }
}
