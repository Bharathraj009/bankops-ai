-- Apply after V1-V6 migrate/validate, as the infrastructure administrator.
-- Reapply after reviewed future migrations: no automatic grants on new tables.
-- Trigger functions remain SECURITY INVOKER; no definer privilege escalation.
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC,bankops_runtime,bankops_reconciliation,bankops_agent,bankops_monitoring;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC,bankops_runtime,bankops_reconciliation,bankops_agent,bankops_monitoring;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC,bankops_runtime,bankops_reconciliation,bankops_agent,bankops_monitoring;
-- Table-level REVOKE does not remove column grants. Reset those as well.
DO $$
DECLARE t RECORD; columns TEXT;
BEGIN
    FOR t IN SELECT c.oid,c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relkind IN ('r','p') LOOP
        SELECT string_agg(quote_ident(attname),',') INTO columns FROM pg_attribute
            WHERE attrelid=t.oid AND attnum>0 AND NOT attisdropped;
        EXECUTE format('REVOKE ALL (%s) ON TABLE public.%I FROM PUBLIC,bankops_runtime,bankops_reconciliation,bankops_agent,bankops_monitoring',columns,t.relname);
    END LOOP;
END $$;
GRANT SELECT ON accounts,transfers,ledger_entries,idempotency_records,customers,customer_sessions,customer_account_ownership TO bankops_runtime;
GRANT INSERT(id,account_number,currency,balance), UPDATE(balance) ON accounts TO bankops_runtime;
GRANT INSERT(id,source_account_id,destination_account_id,amount,currency), UPDATE(status) ON transfers TO bankops_runtime;
GRANT INSERT(id,transfer_id,account_id,entry_type,amount,currency) ON ledger_entries TO bankops_runtime;
GRANT INSERT(id,scope,idempotency_key,request_hash), UPDATE(request_hash,transfer_id) ON idempotency_records TO bankops_runtime;
GRANT INSERT(id,username,password_hash) ON customers TO bankops_runtime;
GRANT INSERT(token_hash,customer_id,expires_at), UPDATE(revoked_at) ON customer_sessions TO bankops_runtime;
GRANT INSERT(account_id,customer_id) ON customer_account_ownership TO bankops_runtime;
GRANT EXECUTE ON FUNCTION create_idempotent_transfer(TEXT,TEXT,TEXT,UUID,UUID,NUMERIC,TEXT) TO bankops_runtime;
GRANT SELECT ON accounts,transfers,ledger_entries,flyway_schema_history TO bankops_reconciliation;
