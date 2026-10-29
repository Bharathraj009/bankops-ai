-- Environment provisioning, not a Flyway migration. Run as the infrastructure
-- administrator in the explicitly selected banking database, before migration.
-- No ownership transfer or financial DML. Existing unsafe roles abort the transaction.
DO $$
DECLARE name TEXT;
BEGIN
    FOREACH name IN ARRAY ARRAY['bankops_migrator','bankops_runtime','bankops_reconciliation','bankops_agent','bankops_monitoring'] LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname=name) THEN
            EXECUTE format('CREATE ROLE %I NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS',name);
        END IF;
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=name AND
            (rolsuper OR rolcreatedb OR rolcreaterole OR rolinherit OR rolreplication OR rolbypassrls))
            OR EXISTS (SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member OR r.oid=m.roleid WHERE r.rolname=name) THEN
            RAISE EXCEPTION 'Unsafe database role configuration';
        END IF;
    END LOOP;
    EXECUTE format('REVOKE ALL ON DATABASE %I FROM PUBLIC',current_database());
    EXECUTE format('REVOKE ALL ON DATABASE %I FROM bankops_migrator,bankops_runtime,bankops_reconciliation,bankops_agent,bankops_monitoring',current_database());
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO bankops_migrator,bankops_runtime,bankops_reconciliation',current_database());
    EXECUTE format('ALTER ROLE bankops_migrator IN DATABASE %I SET search_path=public,pg_catalog',current_database());
    EXECUTE format('ALTER ROLE bankops_runtime IN DATABASE %I SET search_path=pg_catalog,public',current_database());
    EXECUTE format('ALTER ROLE bankops_reconciliation IN DATABASE %I SET search_path=pg_catalog,public',current_database());
    EXECUTE format('ALTER ROLE bankops_reconciliation IN DATABASE %I SET default_transaction_read_only=on',current_database());
END $$;
ALTER ROLE bankops_agent NOLOGIN;
ALTER ROLE bankops_monitoring NOLOGIN;
REVOKE ALL ON SCHEMA public FROM PUBLIC,bankops_runtime,bankops_reconciliation,bankops_agent,bankops_monitoring;
GRANT USAGE,CREATE ON SCHEMA public TO bankops_migrator;
GRANT USAGE ON SCHEMA public TO bankops_runtime,bankops_reconciliation;
-- A global revoke is necessary: a schema-specific revoke cannot remove the
-- built-in global PUBLIC function EXECUTE default. New objects are fail-closed.
ALTER DEFAULT PRIVILEGES FOR ROLE bankops_migrator REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
