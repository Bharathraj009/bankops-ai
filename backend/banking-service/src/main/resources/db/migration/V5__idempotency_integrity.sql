-- V2 already enforces UNIQUE(scope, idempotency_key). Keep claims permanently
-- bound to their original fingerprint and, once assigned, their transfer.
CREATE FUNCTION preserve_idempotency_record() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP IN ('DELETE', 'TRUNCATE') THEN
        RAISE EXCEPTION 'Idempotency records cannot be removed' USING ERRCODE = '23514';
    END IF;
    IF NEW.id IS DISTINCT FROM OLD.id OR NEW.scope IS DISTINCT FROM OLD.scope OR
       NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key OR
       NEW.request_hash IS DISTINCT FROM OLD.request_hash OR
       NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'Idempotency identity and request fingerprint are immutable'
            USING ERRCODE = '23514';
    END IF;
    IF OLD.transfer_id IS NOT NULL AND NEW.transfer_id IS DISTINCT FROM OLD.transfer_id THEN
        RAISE EXCEPTION 'An idempotency key cannot be rebound to another transfer'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER idempotency_immutable BEFORE UPDATE OR DELETE ON idempotency_records
    FOR EACH ROW EXECUTE FUNCTION preserve_idempotency_record();
CREATE TRIGGER idempotency_no_truncate BEFORE TRUNCATE ON idempotency_records
    FOR EACH STATEMENT EXECUTE FUNCTION preserve_idempotency_record();

-- Use this operation for keyed transfer creation. Claim the key BEFORE creating
-- a transfer; PostgreSQL's unique-index conflict handling waits for concurrent
-- claims to commit or roll back. The claim, transfer and binding are transactional.
-- This is not a completion operation: V2-V4 still govern postings and lifecycle.
CREATE FUNCTION create_idempotent_transfer(
    p_scope TEXT, p_key TEXT, p_request_hash TEXT,
    p_source UUID, p_destination UUID, p_amount NUMERIC, p_currency TEXT DEFAULT 'USD'
) RETURNS UUID LANGUAGE plpgsql AS $$
DECLARE
    claim_id UUID;
    target_id UUID;
    existing transfers%ROWTYPE;
BEGIN
    -- Avoid accepting different sub-cent requests through NUMERIC(19,2) rounding.
    IF p_amount IS NULL OR p_amount <= 0 OR p_amount = 'NaN'::NUMERIC OR
       p_amount <> round(p_amount, 2) OR
       p_source IS NULL OR p_destination IS NULL OR p_source = p_destination OR
       p_currency IS DISTINCT FROM 'USD' OR
       p_request_hash IS NULL OR length(btrim(p_request_hash)) = 0 THEN
        RAISE EXCEPTION 'Invalid idempotent transfer request' USING ERRCODE = '23514';
    END IF;

    INSERT INTO idempotency_records(id, scope, idempotency_key, request_hash)
        VALUES (gen_random_uuid(), p_scope, p_key, p_request_hash)
        ON CONFLICT (scope, idempotency_key) DO UPDATE
            SET request_hash = EXCLUDED.request_hash
        RETURNING id, transfer_id INTO claim_id, target_id;
    -- The update trigger rejects a conflicting fingerprint, including under
    -- concurrency. A matching claim stays locked until the transaction ends.
    IF target_id IS NOT NULL THEN
        SELECT * INTO STRICT existing FROM transfers WHERE id = target_id;
        IF existing.source_account_id IS DISTINCT FROM p_source OR
           existing.destination_account_id IS DISTINCT FROM p_destination OR
           existing.amount IS DISTINCT FROM p_amount OR
           existing.currency IS DISTINCT FROM p_currency THEN
            RAISE EXCEPTION 'Idempotency key reused with different transfer details'
                USING ERRCODE = '23514';
        END IF;
        RETURN target_id;
    END IF;

    target_id := gen_random_uuid();
    INSERT INTO transfers(id, source_account_id, destination_account_id, amount, currency)
        VALUES (target_id, p_source, p_destination, p_amount, p_currency);
    UPDATE idempotency_records SET transfer_id = target_id WHERE id = claim_id;
    RETURN target_id;
END;
$$;
