package com.bankops.banking.security;

import org.flywaydb.core.Flyway;

/** Separate non-HTTP migration process. No runtime credentials or banking writes. */
public final class DatabaseMigration {
    private DatabaseMigration() {}
    private static String required(String key) {
        var value=System.getenv(key);
        if(value==null||value.isBlank())throw new IllegalArgumentException("Missing migration configuration");
        return value;
    }
    public static void main(String[] args) {
        // Suppress provider diagnostics: JDBC URLs/errors can contain credentials.
        var context=(ch.qos.logback.classic.LoggerContext)org.slf4j.LoggerFactory.getILoggerFactory();
        context.getLogger(org.slf4j.Logger.ROOT_LOGGER_NAME).setLevel(ch.qos.logback.classic.Level.OFF);
        if(!"local-only".equals(System.getenv("BANKOPS_MIGRATION_APPLY"))) {
            System.err.println("Explicit local migration opt-in required");System.exit(2);return;
        }
        try {
            var user=required("BANKOPS_MIGRATION_DB_USER");
            if(!user.equals("bankops_migrator"))throw new IllegalArgumentException("Use the dedicated migration role");
            var url=required("BANKOPS_MIGRATION_DB_URL");var password=required("BANKOPS_MIGRATION_DB_PASSWORD");
            if(!url.matches("jdbc:postgresql://(localhost|127\\.0\\.0\\.1|\\[::1\\]|host\\.docker\\.internal)(:[0-9]+)?/[A-Za-z0-9_]+(\\?.*)?"))
                throw new IllegalArgumentException("Only explicit local migration targets are supported");
            try(var c=java.sql.DriverManager.getConnection(url,user,password);var s=c.createStatement();var r=s.executeQuery("""
                SELECT current_user='bankops_migrator' AND session_user='bankops_migrator' AND NOT
                    (rolsuper OR rolcreatedb OR rolcreaterole OR rolinherit OR rolreplication OR rolbypassrls)
                FROM pg_roles WHERE rolname=current_user
                """)) {if(!r.next()||!r.getBoolean(1))throw new IllegalArgumentException("Unsafe migration principal");}
            var flyway=Flyway.configure().dataSource(url,user,password)
                .defaultSchema("public").schemas("public").locations("classpath:db/migration")
                .cleanDisabled(true).validateMigrationNaming(true).validateOnMigrate(true).load();
            flyway.migrate();flyway.validate();
            System.out.println("Flyway migrations applied and validated; no application server started");
        } catch (RuntimeException | java.sql.SQLException failure) {
            System.err.println("Migration failed; sensitive diagnostics suppressed");System.exit(1);
        }
    }
}
