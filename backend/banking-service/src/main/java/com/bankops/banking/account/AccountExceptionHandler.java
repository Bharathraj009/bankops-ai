package com.bankops.banking.account;

import com.bankops.banking.account.dto.AccountErrorResponse;
import java.util.Map;
import java.util.TreeMap;
import org.springframework.dao.DataAccessException;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.transaction.TransactionException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

@RestControllerAdvice(assignableTypes = AccountController.class)
public class AccountExceptionHandler {
    @ExceptionHandler(InvalidPaginationException.class)
    public ResponseEntity<AccountErrorResponse> pagination(InvalidPaginationException error) {
        return error(HttpStatus.BAD_REQUEST, "INVALID_PAGINATION", error.getMessage());
    }
    @ExceptionHandler(AccountNotFoundException.class)
    public ResponseEntity<AccountErrorResponse> notFound() {
        return error(HttpStatus.NOT_FOUND, "ACCOUNT_NOT_FOUND", "Account not found");
    }

    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    public ResponseEntity<AccountErrorResponse> invalidId(MethodArgumentTypeMismatchException exception) {
        if (!"accountId".equals(exception.getName())) {
            return error(HttpStatus.BAD_REQUEST, "INVALID_PAGINATION", "Page and size must be valid integers");
        }
        return error(HttpStatus.BAD_REQUEST, "INVALID_ACCOUNT_ID", "Account ID must be a valid UUID");
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<AccountErrorResponse> validation(MethodArgumentNotValidException error) {
        Map<String, String> fields = new TreeMap<>();
        error.getBindingResult().getFieldErrors().forEach(field -> fields.putIfAbsent(field.getField(), field.getDefaultMessage()));
        return ResponseEntity.badRequest().body(new AccountErrorResponse("VALIDATION_ERROR", "Invalid account details", fields));
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<AccountErrorResponse> unreadable() {
        return error(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", "Provide a valid JSON object with only accountNumber and currency");
    }

    @ExceptionHandler(DuplicateKeyException.class)
    public ResponseEntity<AccountErrorResponse> duplicate() {
        return error(HttpStatus.CONFLICT, "ACCOUNT_CONFLICT", "An account with this account number already exists");
    }

    @ExceptionHandler(DataIntegrityViolationException.class)
    public ResponseEntity<AccountErrorResponse> integrity() {
        return error(HttpStatus.INTERNAL_SERVER_ERROR, "ACCOUNT_CREATION_FAILED", "Account could not be created");
    }

    @ExceptionHandler({DataAccessException.class, TransactionException.class})
    public ResponseEntity<AccountErrorResponse> database() {
        return error(HttpStatus.SERVICE_UNAVAILABLE, "DATABASE_UNAVAILABLE", "Account operation could not be completed. Please try again later");
    }

    private ResponseEntity<AccountErrorResponse> error(HttpStatus status, String code, String message) {
        return ResponseEntity.status(status).body(new AccountErrorResponse(code, message, Map.of()));
    }
}
