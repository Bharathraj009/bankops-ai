package com.bankops.banking.customer;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Collections;
import java.util.List;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.web.filter.OncePerRequestFilter;

@Configuration
@EnableMethodSecurity
public class CustomerSecurity {
    @Bean PasswordEncoder customerPasswords() { return new BCryptPasswordEncoder(12); }
    @Bean UserDetailsService customerUsers(CustomerRepository repository) {
        return username -> {
            var c=repository.credentials(username).orElseThrow(()->new UsernameNotFoundException("Invalid credentials"));
            return User.withUsername(c.username()).password(c.hash()).roles("CUSTOMER").disabled(!c.active()).build();
        };
    }
    @Bean AuthenticationManager customerAuthentication(UserDetailsService users,PasswordEncoder passwords) {
        var provider=new DaoAuthenticationProvider(users);provider.setPasswordEncoder(passwords);
        return new ProviderManager(provider);
    }
    static void deny(HttpServletResponse response,int status) throws IOException {
        if(status==401)response.setHeader("WWW-Authenticate","Bearer");
        response.setStatus(status);response.setContentType("application/json");
        response.getWriter().write("{\"error\":\"Access denied\"}");
    }
    @Bean @Order(1) SecurityFilterChain customerChain(HttpSecurity http,CustomerRepository repository,
        org.springframework.core.env.Environment environment,@Value("${bankops.customer.enabled:false}") boolean configured) throws Exception {
        boolean enabled=configured&&!environment.matchesProfiles("prod","production");
        http.securityMatcher("/api/v1/customer/**").csrf(csrf->csrf.disable())
            .sessionManagement(s->s.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .requestCache(c->c.disable()).formLogin(f->f.disable()).httpBasic(b->b.disable()).logout(l->l.disable())
            .authorizeHttpRequests(a->a.requestMatchers("/api/v1/customer/login","/api/v1/customer/register").permitAll().anyRequest().hasRole("CUSTOMER"))
            .exceptionHandling(e->e.authenticationEntryPoint((q,r,x)->deny(r,401)).accessDeniedHandler((q,r,x)->deny(r,403)))
            .addFilterBefore(new OncePerRequestFilter() {
                @Override protected void doFilterInternal(HttpServletRequest q,HttpServletResponse r,FilterChain chain) throws ServletException,IOException {
                    if(!enabled){deny(r,503);return;}
                    var values=Collections.list(q.getHeaders("Authorization"));
                    if (!values.isEmpty()) {
                        if(values.size()!=1 || !values.getFirst().matches("Bearer cus_[A-Za-z0-9_-]{43}")) {deny(r,401);return;}
                        try {
                            var principal=repository.session(values.getFirst().substring(7));
                            if(principal.isEmpty()){deny(r,401);return;}
                            SecurityContextHolder.getContext().setAuthentication(UsernamePasswordAuthenticationToken.authenticated(
                                principal.get(),null,List.of(new SimpleGrantedAuthority("ROLE_CUSTOMER"))));
                        } catch (org.springframework.dao.DataAccessException failure) {deny(r,503);return;}
                    }
                    chain.doFilter(q,r);
                }
            },UsernamePasswordAuthenticationFilter.class);
        return http.build();
    }
    @Bean @Order(2) SecurityFilterChain operatorChain(HttpSecurity http,@Value("${BANKOPS_BANKING_API_TOKEN:}") String token) throws Exception {
        http.csrf(csrf->csrf.disable()).sessionManagement(s->s.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .requestCache(c->c.disable()).formLogin(f->f.disable()).httpBasic(b->b.disable()).logout(l->l.disable())
            .authorizeHttpRequests(a->a.requestMatchers("/api/v1/**").hasRole("OPERATOR").anyRequest().permitAll())
            .exceptionHandling(e->e.authenticationEntryPoint((q,r,x)->deny(r,401)).accessDeniedHandler((q,r,x)->deny(r,403)))
            .addFilterBefore(new OncePerRequestFilter() {
                @Override protected void doFilterInternal(HttpServletRequest q,HttpServletResponse r,FilterChain chain) throws ServletException,IOException {
                    var values=Collections.list(q.getHeaders("Authorization"));
                    if(!token.isEmpty() && values.size()==1 && MessageDigest.isEqual(("Bearer "+token).getBytes(StandardCharsets.UTF_8),values.getFirst().getBytes(StandardCharsets.UTF_8)))
                        SecurityContextHolder.getContext().setAuthentication(UsernamePasswordAuthenticationToken.authenticated(
                            "operator-service",null,List.of(new SimpleGrantedAuthority("ROLE_OPERATOR"))));
                    chain.doFilter(q,r);
                }
            },UsernamePasswordAuthenticationFilter.class);
        return http.build();
    }
}
