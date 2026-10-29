"""Select only GitHub's job-local PostgreSQL service; never read local dotenv files."""
import os
from pathlib import Path


def configuration(env):
    if env.get('GITHUB_ACTIONS') != 'true' or env.get('CI') != 'true':
        raise ValueError('GitHub-hosted CI opt-in required')
    # Never accept a caller-supplied host, JDBC URL, DSN, user or password.
    port = env['CI_POSTGRES_PORT']
    run_id, attempt = env['GITHUB_RUN_ID'], env['GITHUB_RUN_ATTEMPT']
    if not all(value.isascii() and value.isdecimal() for value in (port, run_id, attempt)):
        raise ValueError('Numeric GitHub service/run identifiers required')
    if not 1024 <= int(port) <= 65535:
        raise ValueError('Expected a dynamically published service port')
    password = f'ci-only-{run_id}-{attempt}'
    dsn = f'host=127.0.0.1 port={port} dbname=bankops_test user=bankops_test password={password}'
    return {
        'BANKOPS_TEST_DB_URL': f'jdbc:postgresql://127.0.0.1:{port}/bankops_test',
        'BANKOPS_TEST_DB_USER': 'bankops_test',
        'BANKOPS_TEST_DB_PASSWORD': password,
        'BANKOPS_RECONCILIATION_TEST_DSN': dsn,
        'BANKOPS_DATABASE_SECURITY_TEST_DSN': dsn,
    }


def main():
    values = configuration(os.environ)
    for key, value in values.items():
        if 'PASSWORD' in key or 'DSN' in key:
            print(f'::add-mask::{value}', flush=True)
    with Path(os.environ['GITHUB_ENV']).open('a', encoding='utf-8') as stream:
        for key, value in values.items():
            stream.write(f'{key}={value}\n')
    print('Selected disposable bankops_test on the runner loopback service port')


if __name__ == '__main__':
    main()
