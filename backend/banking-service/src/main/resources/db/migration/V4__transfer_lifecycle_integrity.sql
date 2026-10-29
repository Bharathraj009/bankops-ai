-- Keep V2's deferred ledger validation and V3's transactional balance postings.
-- Completion and postings may occur in either order within one transaction.
CREATE FUNCTION enforce_transfer_lifecycle() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'TRUNCATE' THEN
        RAISE EXCEPTION 'Transfer history cannot be truncated' USING ERRCODE = '23514';
    ELSIF TG_OP = 'DELETE' THEN
        IF OLD.status IN ('COMPLETED', 'FAILED') THEN
            RAISE EXCEPTION 'Terminal transfers cannot be deleted' USING ERRCODE = '23514';
        END IF;
        RETURN OLD;
    ELSIF TG_OP = 'INSERT' THEN
        IF NEW.status IS DISTINCT FROM 'PENDING' THEN
            RAISE EXCEPTION 'Transfers must start PENDING' USING ERRCODE = '23514';
        END IF;
    ELSE
        IF NEW.id IS DISTINCT FROM OLD.id OR
           NEW.amount IS DISTINCT FROM OLD.amount OR
           NEW.source_account_id IS DISTINCT FROM OLD.source_account_id OR
           NEW.destination_account_id IS DISTINCT FROM OLD.destination_account_id OR
           NEW.currency IS DISTINCT FROM OLD.currency THEN
            RAISE EXCEPTION 'Transfer identity, amount, accounts and currency are immutable'
                USING ERRCODE = '23514';
        END IF;
        -- Same-state updates are harmless retries, including in terminal states.
        IF NEW.status IS DISTINCT FROM OLD.status AND
           (OLD.status <> 'PENDING' OR NEW.status NOT IN ('COMPLETED', 'FAILED') OR NEW.status IS NULL) THEN
            RAISE EXCEPTION 'Only PENDING transfers may transition to COMPLETED or FAILED'
                USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER transfer_lifecycle BEFORE INSERT OR UPDATE OR DELETE ON transfers
    FOR EACH ROW EXECUTE FUNCTION enforce_transfer_lifecycle();
CREATE TRIGGER transfer_no_truncate BEFORE TRUNCATE ON transfers
    FOR EACH STATEMENT EXECUTE FUNCTION enforce_transfer_lifecycle();
