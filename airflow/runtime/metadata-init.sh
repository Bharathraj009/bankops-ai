#!/bin/sh
# Fresh metadata volumes only. Never mounted into banking PostgreSQL.
# Password arrives through the container environment, never a shell argument.
set -eu
psql -X --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set ON_ERROR_STOP=1 <<'SQL'
SET log_statement='none';
SET log_min_error_statement='panic';
\getenv runtime_password BANKOPS_AIRFLOW_METADATA_PASSWORD
CREATE ROLE airflow LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD :'runtime_password';
ALTER DATABASE airflow OWNER TO airflow;
REVOKE ALL ON DATABASE airflow FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE,CREATE ON SCHEMA public TO airflow;
SQL
