"""Container-only adapter; reuse reviewed ACLs without widening the host CLI."""
import os
import sys

import psycopg

sys.path.insert(0, '/tools/database')
from provision import PASSWORDS, grant, prepare  # noqa: E402


def main():
    if os.environ.get('BANKOPS_LOCAL_COMPOSE') != 'isolated':
        raise SystemExit('Isolated Compose opt-in required')
    try:
        passwords = {role: os.environ[key] for role, key in PASSWORDS.items()}
        admin = os.environ['BANKOPS_POSTGRES_ADMIN_PASSWORD']
        if admin in passwords.values():
            raise ValueError('Distinct administrator required')
        # Shares postgres network namespace; no remote-target override exists.
        with psycopg.connect(host='127.0.0.1', dbname='bankops', user='bankops',
                              password=admin, connect_timeout=5) as connection:
            if sys.argv[1:] == ['prepare']:
                prepare(connection, passwords)
            elif sys.argv[1:] == ['grant']:
                grant(connection)
            else:
                raise ValueError('Unknown operation')
        print('Local database ACL operation committed')
    except (psycopg.Error, ValueError, KeyError):
        raise SystemExit('Database ACL operation failed; details suppressed') from None


if __name__ == '__main__':
    main()
