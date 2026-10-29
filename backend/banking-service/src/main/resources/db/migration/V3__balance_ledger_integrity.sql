-- V2 postings did not move money. Refuse to silently bless historical postings:
-- they require an explicit reconciliation before this migration can run.
LOCK TABLE transfers, ledger_entries, accounts IN ACCESS EXCLUSIVE MODE;
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM ledger_entries) THEN
        RAISE EXCEPTION 'Reconcile V2 ledger entries before installing balance integrity';
    END IF;
END $$;

ALTER TABLE accounts ADD COLUMN opening_balance NUMERIC(19,2);
UPDATE accounts SET opening_balance = balance;
ALTER TABLE accounts ALTER COLUMN opening_balance SET NOT NULL;

CREATE FUNCTION preserve_opening_balance() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        NEW.opening_balance := NEW.balance;
    ELSIF NEW.opening_balance IS DISTINCT FROM OLD.opening_balance THEN
        RAISE EXCEPTION 'Opening balance is immutable' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER account_opening_balance BEFORE INSERT OR UPDATE ON accounts
    FOR EACH ROW EXECUTE FUNCTION preserve_opening_balance();

CREATE FUNCTION apply_ledger_balance() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE t transfers%ROWTYPE;
BEGIN
    SELECT * INTO STRICT t FROM transfers WHERE id = NEW.transfer_id FOR UPDATE;
    -- Always lock both accounts in UUID order, including for opposite transfers.
    PERFORM id FROM accounts WHERE id IN (t.source_account_id, t.destination_account_id)
        ORDER BY id FOR UPDATE;
    UPDATE accounts SET balance = balance +
        CASE WHEN NEW.entry_type = 'DEBIT' THEN -NEW.amount ELSE NEW.amount END
        WHERE id = NEW.account_id;
    RETURN NEW;
END;
$$;
CREATE TRIGGER ledger_apply_balance AFTER INSERT ON ledger_entries
    FOR EACH ROW EXECUTE FUNCTION apply_ledger_balance();

CREATE FUNCTION validate_account_balance() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE actual NUMERIC; expected NUMERIC;
BEGIN
    SELECT balance, opening_balance INTO actual, expected FROM accounts
        WHERE id = NEW.id FOR UPDATE;
    IF NOT FOUND THEN RETURN NULL; END IF;
    SELECT expected + coalesce(sum(CASE WHEN entry_type = 'CREDIT' THEN amount ELSE -amount END), 0)
        INTO expected FROM ledger_entries WHERE account_id = NEW.id;
    IF actual <> expected THEN
        RAISE EXCEPTION 'Account % balance must match ledger postings', NEW.id USING ERRCODE = '23514';
    END IF;
    RETURN NULL;
END;
$$;
CREATE CONSTRAINT TRIGGER account_balance_at_commit AFTER INSERT OR UPDATE ON accounts
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION validate_account_balance();
