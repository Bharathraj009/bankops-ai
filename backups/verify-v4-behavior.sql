\set ON_ERROR_STOP on
BEGIN;
-- All probe rows and changes are rolled back; existing rows are never touched.
DO $$
DECLARE
    a UUID := gen_random_uuid(); b UUID := gen_random_uuid(); other UUID := gen_random_uuid();
    completed UUID := gen_random_uuid(); failed UUID := gen_random_uuid();
    missing UUID := gen_random_uuid(); overdraft UUID := gen_random_uuid();
BEGIN
    INSERT INTO accounts(id,account_number,balance) VALUES
        (a,a::text,100),(b,b::text,100),(other,other::text,100);
    INSERT INTO transfers(id,source_account_id,destination_account_id,amount) VALUES
        (completed,a,b,10),(failed,a,b,10),(missing,a,b,10),(overdraft,a,b,101);
    -- Valid completion, with status first and deferred double-entry validation.
    UPDATE transfers SET status='COMPLETED' WHERE id=completed;
    INSERT INTO ledger_entries(id,transfer_id,account_id,entry_type,amount) VALUES
        (gen_random_uuid(),completed,a,'DEBIT',10),(gen_random_uuid(),completed,b,'CREDIT',10);
    UPDATE transfers SET status='FAILED' WHERE id=failed;
    SET CONSTRAINTS ALL IMMEDIATE;
    IF (SELECT balance FROM accounts WHERE id=a) <> 90 OR
       (SELECT balance FROM accounts WHERE id=b) <> 110 THEN
        RAISE EXCEPTION 'Valid completion did not move money correctly';
    END IF;
    SET CONSTRAINTS ALL DEFERRED;

    BEGIN
        INSERT INTO transfers(id,source_account_id,destination_account_id,amount,status)
            VALUES(gen_random_uuid(),a,b,10,'FAILED');
        RAISE EXCEPTION 'Terminal creation unexpectedly accepted';
    EXCEPTION WHEN check_violation THEN NULL; END;
    BEGIN
        UPDATE transfers SET status='PENDING' WHERE id=completed;
        RAISE EXCEPTION 'Completed transfer reopened';
    EXCEPTION WHEN check_violation THEN NULL; END;
    BEGIN
        UPDATE transfers SET status='COMPLETED' WHERE id=failed;
        RAISE EXCEPTION 'Failed transfer completed';
    EXCEPTION WHEN check_violation THEN NULL; END;
    BEGIN
        UPDATE transfers SET amount=11 WHERE id=missing;
        RAISE EXCEPTION 'Transfer amount changed';
    EXCEPTION WHEN check_violation THEN NULL; END;
    BEGIN
        UPDATE transfers SET source_account_id=other WHERE id=missing;
        RAISE EXCEPTION 'Transfer source changed';
    EXCEPTION WHEN check_violation THEN NULL; END;
    BEGIN
        UPDATE transfers SET destination_account_id=other WHERE id=missing;
        RAISE EXCEPTION 'Transfer destination changed';
    EXCEPTION WHEN check_violation THEN NULL; END;
    BEGIN
        UPDATE transfers SET status='COMPLETED' WHERE id=missing;
        SET CONSTRAINTS ALL IMMEDIATE;
        RAISE EXCEPTION 'Completion without postings accepted';
    EXCEPTION WHEN check_violation THEN NULL; END;
    BEGIN
        INSERT INTO ledger_entries(id,transfer_id,account_id,entry_type,amount) VALUES
            (gen_random_uuid(),failed,a,'DEBIT',10),(gen_random_uuid(),failed,b,'CREDIT',10);
        SET CONSTRAINTS ALL IMMEDIATE;
        RAISE EXCEPTION 'Failed transfer received postings';
    EXCEPTION WHEN check_violation THEN NULL; END;
    BEGIN
        INSERT INTO ledger_entries(id,transfer_id,account_id,entry_type,amount)
            VALUES(gen_random_uuid(),overdraft,b,'CREDIT',101);
        INSERT INTO ledger_entries(id,transfer_id,account_id,entry_type,amount)
            VALUES(gen_random_uuid(),overdraft,a,'DEBIT',101);
        RAISE EXCEPTION 'Insufficient-funds debit accepted';
    EXCEPTION WHEN check_violation THEN NULL; END;
    BEGIN
        UPDATE accounts SET balance=100 WHERE id=a;
        SET CONSTRAINTS ALL IMMEDIATE;
        RAISE EXCEPTION 'Balance tampering accepted';
    EXCEPTION WHEN check_violation THEN NULL; END;
    BEGIN
        UPDATE ledger_entries SET amount=11 WHERE transfer_id=completed;
        RAISE EXCEPTION 'Ledger mutation accepted';
    EXCEPTION WHEN check_violation THEN NULL; END;
    UPDATE transfers SET status='COMPLETED' WHERE id=completed;
    UPDATE transfers SET status='FAILED' WHERE id=failed;
    SET CONSTRAINTS ALL IMMEDIATE;
    IF (SELECT balance FROM accounts WHERE id=a) <> 90 OR
       (SELECT balance FROM accounts WHERE id=b) <> 110 OR
       (SELECT count(*) FROM ledger_entries WHERE transfer_id IN (failed,missing,overdraft)) <> 0 THEN
        RAISE EXCEPTION 'Rejected operations did not roll back cleanly';
    END IF;
    RAISE NOTICE 'Lifecycle, ledger, balance and insufficient-funds probes passed';
END $$;
ROLLBACK;
