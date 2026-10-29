package com.bankops.banking.transfer;

import com.bankops.banking.dev.DevFundingController;

import java.util.Map;
import java.util.TreeMap;
import org.springframework.dao.DataAccessException;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.transaction.TransactionException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingRequestHeaderException;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

@RestControllerAdvice(assignableTypes = {TransferController.class, DevFundingController.class})
public class TransferExceptionHandler {
    public record Error(String code, String message, Map<String, String> fields) {}
    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    public ResponseEntity<Error> invalidId(MethodArgumentTypeMismatchException error) {
        if ("accountId".equals(error.getName())) {
            return response(HttpStatus.BAD_REQUEST, "INVALID_ACCOUNT_ID", "Account ID must be a valid UUID");
        }
        return response(HttpStatus.BAD_REQUEST, "INVALID_TRANSFER_ID", "Transfer ID must be a valid UUID");
    }
    @ExceptionHandler(TransferRequestException.class)
    public ResponseEntity<Error> request(TransferRequestException error) {
        return response(error.status(), error.code(), error.getMessage());
    }
    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Error> validation(MethodArgumentNotValidException error) {
        Map<String, String> fields = new TreeMap<>();
        error.getBindingResult().getFieldErrors().forEach(field -> fields.putIfAbsent(field.getField(), field.getDefaultMessage()));
        return ResponseEntity.badRequest().body(new Error("VALIDATION_ERROR", "Invalid transfer details", fields));
    }
    @ExceptionHandler(MissingRequestHeaderException.class)
    public ResponseEntity<Error> missingKey() {
        return response(HttpStatus.BAD_REQUEST, "INVALID_IDEMPOTENCY_KEY", "Idempotency-Key is required");
    }
    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<Error> unreadable() {
        return response(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", "Provide valid request fields and a positive USD amount");
    }
    @ExceptionHandler({DataIntegrityViolationException.class, IllegalStateException.class})
    public ResponseEntity<Error> integrity() {
        return response(HttpStatus.INTERNAL_SERVER_ERROR, "TRANSFER_FAILED", "Transfer could not be completed");
    }
    @ExceptionHandler({DataAccessException.class, TransactionException.class})
    public ResponseEntity<Error> database() {
        return response(HttpStatus.SERVICE_UNAVAILABLE, "DATABASE_UNAVAILABLE", "Transfer could not be completed. Please retry with the same Idempotency-Key");
    }
    private ResponseEntity<Error> response(HttpStatus status, String code, String message) {
        return ResponseEntity.status(status).body(new Error(code, message, Map.of()));
    }
}
