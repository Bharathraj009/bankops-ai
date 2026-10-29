\set ON_ERROR_STOP on
BEGIN;
DO $$
DECLARE
    a UUID := gen_random_uuid(); b UUID := gen_random_uuid(); other UUID := gen_random_uuid();
    scope TEXT := gen_random_uuid()::text; key TEXT := gen_random_uuid()::text;
    t UUID; retry UUID; alternate UUID; failed UUID;
BEGIN
    INSERT INTO accounts(id,account_number,balance) VALUES (a,a::text,100),(b,b::text,100),(other,other::text,100);
    t := create_idempotent_transfer(scope,key,'fingerprint-a',a,b,10);
    retry := create_idempotent_transfer(scope,key,'fingerprint-a',a,b,10);
    IF retry <> t THEN RAISE EXCEPTION 'Matching pending retry created another transfer'; END IF;
    BEGIN
        PERFORM create_idempotent_transfer(scope,key,'fingerprint-b',a,b,10);
        RAISE EXCEPTION 'Different fingerprint accepted';
    EXCEPTION WHEN check_violation THEN NULL; END;
    BEGIN
        PERFORM create_idempotent_transfer(scope,key,'fingerprint-a',a,b,11);
        RAISE EXCEPTION 'Different amount accepted';
    EXCEPTION WHEN check_violation THEN NULL; END;
    BEGIN
        PERFORM create_idempotent_transfer(scope,key,'fingerprint-a',other,b,10);
        RAISE EXCEPTION 'Different source accepted';
    EXCEPTION WHEN check_violation THEN NULL; END;
    BEGIN
        PERFORM create_idempotent_transfer(scope,key,'fingerprint-a',a,other,10);
        RAISE EXCEPTION 'Different destination accepted';
    EXCEPTION WHEN check_violation THEN NULL; END;
    BEGIN
        INSERT INTO idempotency_records(id,scope,idempotency_key,request_hash)
            VALUES(gen_random_uuid(),scope,key,'fingerprint-a');
        RAISE EXCEPTION 'Duplicate scoped key accepted';
    EXCEPTION WHEN unique_violation THEN NULL; END;
    BEGIN
        UPDATE idempotency_records SET request_hash='changed' WHERE transfer_id=t;
        RAISE EXCEPTION 'Stored fingerprint changed';
    EXCEPTION WHEN check_violation THEN NULL; END;
    BEGIN
        UPDATE idempotency_records SET scope='changed' WHERE transfer_id=t;
        RAISE EXCEPTION 'Stored scope changed';
    EXCEPTION WHEN check_violation THEN NULL; END;
    BEGIN
        UPDATE idempotency_records SET idempotency_key='changed' WHERE transfer_id=t;
        RAISE EXCEPTION 'Stored key changed';
    EXCEPTION WHEN check_violation THEN NULL; END;
    BEGIN
        UPDATE idempotency_records SET transfer_id=NULL WHERE transfer_id=t;
        RAISE EXCEPTION 'Transfer binding removed';
    EXCEPTION WHEN check_violation THEN NULL; END;
    alternate := create_idempotent_transfer(scope || '-other',key,'fingerprint-other',a,b,10);
    IF alternate=t THEN RAISE EXCEPTION 'Different scopes were conflated'; END IF;
    BEGIN
        UPDATE idempotency_records SET transfer_id=alternate WHERE transfer_id=t;
        RAISE EXCEPTION 'Transfer binding replaced';
    EXCEPTION WHEN check_violation THEN NULL; END;
    INSERT INTO ledger_entries(id,transfer_id,account_id,entry_type,amount) VALUES
        (gen_random_uuid(),t,a,'DEBIT',10),(gen_random_uuid(),t,b,'CREDIT',10);
    UPDATE transfers SET status='COMPLETED' WHERE id=t;
    retry := create_idempotent_transfer(scope,key,'fingerprint-a',a,b,10);
    IF retry<>t THEN RAISE EXCEPTION 'Matching completed retry created another transfer'; END IF;
    failed := create_idempotent_transfer(scope,key || '-failed','fingerprint-failed',a,b,10);
    UPDATE transfers SET status='FAILED' WHERE id=failed;
    retry := create_idempotent_transfer(scope,key || '-failed','fingerprint-failed',a,b,10);
    IF retry<>failed THEN RAISE EXCEPTION 'Matching failed retry created another transfer'; END IF;
    SET CONSTRAINTS ALL IMMEDIATE;
    IF (SELECT balance FROM accounts WHERE id=a)<>90 OR (SELECT balance FROM accounts WHERE id=b)<>110 OR
       (SELECT count(*) FROM transfers WHERE source_account_id=a)<>3 OR
       (SELECT count(*) FROM ledger_entries WHERE transfer_id=t)<>2 THEN
        RAISE EXCEPTION 'Idempotency probes changed balances or created extra transfers';
    END IF;
    RAISE NOTICE 'Scoped uniqueness, immutability, matching retries and conflicting requests passed';
END $$;
ROLLBACK;
