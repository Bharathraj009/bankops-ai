package com.bankops.banking.customer;

import com.fasterxml.jackson.annotation.JsonAnySetter;
import com.fasterxml.jackson.annotation.JsonIgnore;
import jakarta.validation.constraints.*;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.time.OffsetDateTime;
import java.util.Base64;
import java.util.HashMap;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class CustomerAuthService {
    public record Credentials(@NotNull @Pattern(regexp="[a-z0-9][a-z0-9._-]{2,63}") String username,
        @NotBlank @Size(min=12,max=72) String password) {
        @JsonIgnore @AssertTrue public boolean isPasswordWithinLimit() { return password==null || password.getBytes(StandardCharsets.UTF_8).length<=72; }
        @JsonAnySetter public void unknown(String key,Object value) {throw new IllegalArgumentException("Unsupported field");}
        @Override public String toString() {return "Credentials[REDACTED]";}
    }
    public record Session(String token,OffsetDateTime expiresAt) {
        @Override public String toString() {return "Session[REDACTED]";}
    }
    private record Attempts(long window,int count) {}
    private final Map<String,Attempts> attempts=new HashMap<>();
    private final int maxAttempts;
    private final CustomerRepository customers;
    private final AuthenticationManager authentication;
    private final PasswordEncoder passwords;
    private final JdbcTemplate jdbc;
    private final SecureRandom random=new SecureRandom();
    public CustomerAuthService(CustomerRepository customers,AuthenticationManager authentication,PasswordEncoder passwords,JdbcTemplate jdbc,
        @Value("${bankops.customer.auth.max-attempts:30}") int maxAttempts) {
        this.customers=customers;this.authentication=authentication;this.passwords=passwords;this.jdbc=jdbc;this.maxAttempts=maxAttempts;
        if(maxAttempts<1)throw new IllegalArgumentException("Invalid authentication rate limit");
    }
    // Bounded, process-local throttling. Never trust X-Forwarded-For from clients.
    public synchronized void attempt(String address) {
        long now=System.currentTimeMillis();
        attempts.entrySet().removeIf(e->now-e.getValue().window()>60000);
        var prior=attempts.get(address);
        if((prior==null && attempts.size()>=1024) || (prior!=null && prior.count()>=maxAttempts))
            throw new ResponseStatusException(HttpStatus.TOO_MANY_REQUESTS);
        attempts.put(address,new Attempts(prior==null?now:prior.window(),prior==null?1:prior.count()+1));
    }
    @Transactional public CustomerPrincipal register(Credentials request) {
        return customers.register(request.username(),passwords.encode(request.password()));
    }
    @Transactional public Session login(Credentials request) {
        authentication.authenticate(UsernamePasswordAuthenticationToken.unauthenticated(request.username(),request.password()));
        var customer=customers.credentials(request.username()).orElseThrow();
        byte[] bytes=new byte[32];random.nextBytes(bytes);
        String token="cus_"+Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
        return jdbc.queryForObject("""
            INSERT INTO customer_sessions(token_hash,customer_id,expires_at)
            VALUES (?,?,CURRENT_TIMESTAMP+INTERVAL '15 minutes') RETURNING expires_at
            """,(r,n)->new Session(token,r.getObject("expires_at",OffsetDateTime.class)),CustomerRepository.digest(token),customer.id());
    }
}
