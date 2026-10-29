package com.bankops.banking.customer;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.Optional;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class CustomerRepository {
    public record Credentials(UUID id, String username, String hash, boolean active) {
        @Override public String toString() { return "CustomerCredentials[REDACTED]"; }
    }
    private final JdbcTemplate jdbc;
    public CustomerRepository(JdbcTemplate jdbc) { this.jdbc = jdbc; }
    public Optional<Credentials> credentials(String username) {
        return jdbc.query("SELECT id,username,password_hash,active FROM customers WHERE username=?",
            (r,n)->new Credentials(r.getObject("id",UUID.class),r.getString("username"),r.getString("password_hash"),r.getBoolean("active")),username).stream().findFirst();
    }
    public CustomerPrincipal register(String username, String hash) {
        var id=UUID.randomUUID();
        jdbc.update("INSERT INTO customers(id,username,password_hash) VALUES (?,?,?)",id,username,hash);
        return new CustomerPrincipal(id,username);
    }
    public Optional<CustomerPrincipal> session(String token) {
        return jdbc.query("""
            SELECT c.id,c.username FROM customer_sessions s JOIN customers c ON c.id=s.customer_id
            WHERE s.token_hash=? AND s.revoked_at IS NULL AND s.expires_at>CURRENT_TIMESTAMP AND c.active
            """, (r,n)->new CustomerPrincipal(r.getObject("id",UUID.class),r.getString("username")),digest(token)).stream().findFirst();
    }
    public void revoke(String token) {
        jdbc.update("UPDATE customer_sessions SET revoked_at=CURRENT_TIMESTAMP WHERE token_hash=? AND revoked_at IS NULL",digest(token));
    }
    public boolean owns(UUID account,UUID customer) {
        return Boolean.TRUE.equals(jdbc.queryForObject("SELECT EXISTS(SELECT 1 FROM customer_account_ownership WHERE account_id=? AND customer_id=?)",Boolean.class,account,customer));
    }
    public boolean hasOwner(UUID account) {
        return Boolean.TRUE.equals(jdbc.queryForObject("SELECT EXISTS(SELECT 1 FROM customer_account_ownership WHERE account_id=?)",Boolean.class,account));
    }
    public void assignNew(UUID account,UUID customer) {
        jdbc.update("INSERT INTO customer_account_ownership(account_id,customer_id) VALUES (?,?)",account,customer);
    }
    public static String digest(String value) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8))); }
        catch (java.security.NoSuchAlgorithmException error) { throw new IllegalStateException("SHA-256 unavailable"); }
    }
}
