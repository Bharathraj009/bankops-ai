"""Actual PostgreSQL verifies the generated SCRAM verifier; disposable DSN only."""
import importlib.util
import os
from pathlib import Path
import secrets
from uuid import uuid4

import psycopg
from psycopg import sql
import pytest


def test_postgresql_accepts_scram_and_rejects_wrong_password():
    dsn=os.environ['BANKOPS_DATABASE_SECURITY_TEST_DSN']
    spec=importlib.util.spec_from_file_location('provision',Path(__file__).resolve().parents[1]/'provision.py')
    provision=importlib.util.module_from_spec(spec);spec.loader.exec_module(provision)
    role='scram_test_'+uuid4().hex;password=secrets.token_urlsafe(40)
    with psycopg.connect(dsn) as admin:
        admin.execute("SET LOCAL log_statement='none'");admin.execute("SET LOCAL log_min_error_statement='panic'")
        admin.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD {}').format(sql.Identifier(role),sql.Literal(provision.scram(password))))
    parameters=psycopg.conninfo.conninfo_to_dict(dsn)|{'user':role,'password':password}
    with psycopg.connect(**parameters) as runtime:
        assert runtime.execute('SELECT current_user').fetchone()[0]==role
    parameters['password']=secrets.token_urlsafe(40)
    with pytest.raises(psycopg.OperationalError):psycopg.connect(**parameters)
