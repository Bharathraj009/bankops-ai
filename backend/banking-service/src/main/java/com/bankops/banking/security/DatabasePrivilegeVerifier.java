package com.bankops.banking.security;

import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

/** Fail closed at startup; never logs SQL, identities or credentials. */
@Component
@ConditionalOnProperty(name="bankops.database.verify-runtime",havingValue="true")
public class DatabasePrivilegeVerifier implements SmartInitializingSingleton {
    private final JdbcTemplate jdbc;
    public DatabasePrivilegeVerifier(JdbcTemplate jdbc) {this.jdbc=jdbc;}
    // Complete before the web server lifecycle starts accepting HTTP requests.
    @Override public void afterSingletonsInstantiated() {verify();}
    public void verify() {
        try {
            boolean unsafe=Boolean.TRUE.equals(jdbc.queryForObject("""
                SELECT current_user <> 'bankops_runtime' OR session_user <> 'bankops_runtime'
                OR EXISTS(SELECT 1 FROM pg_roles WHERE rolname IN (current_user,session_user) AND
                    (rolsuper OR rolcreatedb OR rolcreaterole OR rolinherit OR rolreplication OR rolbypassrls))
                OR EXISTS(SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member OR r.oid=m.roleid WHERE r.rolname=current_user)
                OR has_database_privilege(current_user,current_database(),'CREATE,TEMP')
                OR EXISTS(SELECT 1 FROM pg_namespace WHERE nspname !~ '^pg_' AND nspname<>'information_schema'
                    AND (nspowner=(SELECT oid FROM pg_roles WHERE rolname=current_user) OR has_schema_privilege(current_user,oid,'CREATE')))
                OR EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND
                    (c.relowner=(SELECT oid FROM pg_roles WHERE rolname=current_user) OR
                     (c.relkind IN ('r','p') AND has_table_privilege(current_user,c.oid,'DELETE,TRUNCATE,TRIGGER,REFERENCES'))))
                OR EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public'
                    AND (p.prosecdef OR (p.proname<>'create_idempotent_transfer' AND has_function_privilege(current_user,p.oid,'EXECUTE'))))
                OR has_table_privilege(current_user,'public.flyway_schema_history','SELECT,INSERT,UPDATE,DELETE')
                """,Boolean.class));
            if(unsafe)throw new IllegalStateException("Unsafe database runtime privileges");
        } catch (org.springframework.dao.DataAccessException error) {
            throw new IllegalStateException("Database runtime privilege verification failed");
        }
    }
}
