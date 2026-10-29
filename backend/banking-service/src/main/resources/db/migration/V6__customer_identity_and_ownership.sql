-- Metadata only. Never infer ownership or update existing financial records.
CREATE TABLE customers (
    id UUID PRIMARY KEY,
    username VARCHAR(64) NOT NULL UNIQUE CHECK (username ~ '^[a-z0-9][a-z0-9._-]{2,63}$'),
    password_hash VARCHAR(60) NOT NULL CHECK (password_hash ~ '^\$2[aby]\$12\$[./A-Za-z0-9]{53}$'),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE customer_account_ownership (
    account_id UUID PRIMARY KEY REFERENCES accounts(id),
    customer_id UUID NOT NULL REFERENCES customers(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX customer_accounts_owner_idx ON customer_account_ownership(customer_id, account_id);
CREATE FUNCTION preserve_customer_ownership() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Account ownership cannot be changed or removed' USING ERRCODE = '23514';
END;
$$;
CREATE TRIGGER customer_ownership_immutable BEFORE UPDATE OR DELETE ON customer_account_ownership
    FOR EACH ROW EXECUTE FUNCTION preserve_customer_ownership();
CREATE TRIGGER customer_ownership_no_truncate BEFORE TRUNCATE ON customer_account_ownership
    FOR EACH STATEMENT EXECUTE FUNCTION preserve_customer_ownership();
CREATE TABLE customer_sessions (
    token_hash CHAR(64) PRIMARY KEY CHECK (token_hash ~ '^[0-9a-f]{64}$'),
    customer_id UUID NOT NULL REFERENCES customers(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    CHECK (expires_at > created_at)
);
CREATE INDEX customer_sessions_customer_idx ON customer_sessions(customer_id);
