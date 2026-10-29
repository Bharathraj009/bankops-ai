CREATE TABLE accounts (
    id UUID PRIMARY KEY,
    account_number VARCHAR(64) NOT NULL UNIQUE,
    currency VARCHAR(3) NOT NULL DEFAULT 'USD' CHECK (currency = 'USD'),
    balance NUMERIC(19,2) NOT NULL DEFAULT 0 CHECK (balance >= 0 AND balance <> 'NaN'::NUMERIC),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE transfers (
    id UUID PRIMARY KEY,
    source_account_id UUID NOT NULL REFERENCES accounts(id),
    destination_account_id UUID NOT NULL REFERENCES accounts(id),
    amount NUMERIC(19,2) NOT NULL CHECK (amount > 0 AND amount <> 'NaN'::NUMERIC),
    currency VARCHAR(3) NOT NULL DEFAULT 'USD' CHECK (currency = 'USD'),
    status VARCHAR(16) NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'COMPLETED', 'FAILED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (source_account_id <> destination_account_id)
);
CREATE INDEX transfers_source_account_idx ON transfers(source_account_id);
CREATE INDEX transfers_destination_account_idx ON transfers(destination_account_id);
CREATE INDEX transfers_status_created_at_idx ON transfers(status, created_at);

CREATE TABLE ledger_entries (
    id UUID PRIMARY KEY,
    transfer_id UUID NOT NULL REFERENCES transfers(id),
    account_id UUID NOT NULL REFERENCES accounts(id),
    entry_type VARCHAR(6) NOT NULL CHECK (entry_type IN ('DEBIT', 'CREDIT')),
    amount NUMERIC(19,2) NOT NULL CHECK (amount > 0 AND amount <> 'NaN'::NUMERIC),
    currency VARCHAR(3) NOT NULL DEFAULT 'USD' CHECK (currency = 'USD'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (transfer_id, entry_type)
);
CREATE INDEX ledger_entries_account_created_at_idx ON ledger_entries(account_id, created_at);

CREATE TABLE idempotency_records (
    id UUID PRIMARY KEY,
    scope VARCHAR(128) NOT NULL CHECK (length(btrim(scope)) > 0),
    idempotency_key VARCHAR(255) NOT NULL CHECK (length(btrim(idempotency_key)) > 0),
    request_hash VARCHAR(64) NOT NULL,
    transfer_id UUID REFERENCES transfers(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (scope, idempotency_key)
);
CREATE INDEX idempotency_records_transfer_idx ON idempotency_records(transfer_id);

-- Serialize postings with transfer updates so concurrent writers cannot bypass
-- the deferred checks. A transfer has one debit and one credit posting.
CREATE FUNCTION lock_ledger_transfer() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    PERFORM 1 FROM transfers WHERE id = NEW.transfer_id FOR UPDATE;
    RETURN NEW;
END;
$$;
CREATE TRIGGER ledger_transfer_lock BEFORE INSERT ON ledger_entries
    FOR EACH ROW EXECUTE FUNCTION lock_ledger_transfer();

CREATE FUNCTION reject_ledger_mutation() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Ledger entries are immutable' USING ERRCODE = '23514';
END;
$$;
CREATE TRIGGER ledger_immutable BEFORE UPDATE OR DELETE ON ledger_entries
    FOR EACH ROW EXECUTE FUNCTION reject_ledger_mutation();
CREATE TRIGGER ledger_no_truncate BEFORE TRUNCATE ON ledger_entries
    FOR EACH STATEMENT EXECUTE FUNCTION reject_ledger_mutation();

CREATE FUNCTION validate_transfer_ledger() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    target_id UUID;
    transfer_row transfers%ROWTYPE;
    posting_count INTEGER;
    debit_total NUMERIC;
    credit_total NUMERIC;
    invalid_accounts INTEGER;
BEGIN
    IF TG_TABLE_NAME = 'transfers' THEN
        target_id := NEW.id;
    ELSE
        target_id := NEW.transfer_id;
    END IF;
    SELECT * INTO transfer_row FROM transfers WHERE id = target_id FOR UPDATE;
    IF NOT FOUND THEN
        RETURN NULL;
    END IF;
    SELECT count(*),
           coalesce(sum(amount) FILTER (WHERE entry_type = 'DEBIT'), 0),
           coalesce(sum(amount) FILTER (WHERE entry_type = 'CREDIT'), 0),
           count(*) FILTER (WHERE
               (entry_type = 'DEBIT' AND account_id <> transfer_row.source_account_id) OR
               (entry_type = 'CREDIT' AND account_id <> transfer_row.destination_account_id))
      INTO posting_count, debit_total, credit_total, invalid_accounts
      FROM ledger_entries WHERE transfer_id = target_id;
    IF debit_total <> credit_total OR invalid_accounts <> 0 OR
       (posting_count > 0 AND
           (posting_count <> 2 OR debit_total <> transfer_row.amount)) OR
       (transfer_row.status = 'COMPLETED' AND posting_count <> 2) OR
       (transfer_row.status = 'FAILED' AND posting_count <> 0) THEN
        RAISE EXCEPTION 'Transfer % requires balanced ledger postings matching its accounts and amount', target_id
            USING ERRCODE = '23514';
    END IF;
    RETURN NULL;
END;
$$;
CREATE CONSTRAINT TRIGGER ledger_balance_at_commit
    AFTER INSERT ON ledger_entries DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION validate_transfer_ledger();
CREATE CONSTRAINT TRIGGER transfer_ledger_at_commit
    AFTER INSERT OR UPDATE ON transfers DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION validate_transfer_ledger();
