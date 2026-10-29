package com.bankops.banking.customer;

import com.bankops.banking.account.AccountNotFoundException;
import com.bankops.banking.account.InvalidPaginationException;
import com.bankops.banking.transfer.TransferRequestException;
import java.util.Map;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.dao.DataAccessException;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.transaction.TransactionException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ResponseStatusException;

@RestControllerAdvice(assignableTypes=CustomerController.class)
@Order(Ordered.HIGHEST_PRECEDENCE)
public class CustomerErrors {
    private ResponseEntity<?> error(int status,String code) {return ResponseEntity.status(status).body(Map.of("error",code));}
    @ExceptionHandler(AuthenticationException.class) public ResponseEntity<?> authentication() {return error(401,"Authentication failed");}
    @ExceptionHandler(AccessDeniedException.class) public ResponseEntity<?> denied() {return error(403,"Access denied");}
    @ExceptionHandler(AccountNotFoundException.class) public ResponseEntity<?> missing() {return error(404,"Account not found");}
    @ExceptionHandler(TransferRequestException.class) public ResponseEntity<?> transfer(TransferRequestException e) {return error(e.status().value(),e.code());}
    @ExceptionHandler(DuplicateKeyException.class) public ResponseEntity<?> duplicate() {return error(409,"Conflict");}
    @ExceptionHandler(ResponseStatusException.class) public ResponseEntity<?> limited(ResponseStatusException e) {return error(e.getStatusCode().value(),"Request unavailable");}
    @ExceptionHandler({DataAccessException.class,TransactionException.class}) public ResponseEntity<?> database() {return error(503,"Service unavailable");}
    @ExceptionHandler({org.springframework.web.bind.MethodArgumentNotValidException.class,
        org.springframework.http.converter.HttpMessageNotReadableException.class,
        org.springframework.web.method.annotation.MethodArgumentTypeMismatchException.class,
        org.springframework.web.bind.MissingRequestHeaderException.class,InvalidPaginationException.class})
    public ResponseEntity<?> invalid() {return error(400,"Invalid request");}
}
