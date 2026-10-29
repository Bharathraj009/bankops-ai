package com.bankops.banking.account;

public class InvalidPaginationException extends RuntimeException {
    public InvalidPaginationException() { super("Page must be nonnegative and size must be between 1 and 100"); }
}
