"""Generate fresh local-only credentials without printing secrets or replacing files."""
import hashlib
from pathlib import Path
import secrets

ROOT = Path(__file__).resolve().parent


def generate(root=ROOT, prefix='bankops-step67-'):
    destination = root / '.env.local'
    if destination.exists() or (root / '.secrets').exists():
        raise SystemExit('Local configuration already exists; refusing to replace credentials')
    names = ('BANKOPS_POSTGRES_ADMIN_PASSWORD', 'BANKOPS_MIGRATION_DB_PASSWORD',
             'BANKOPS_DB_PASSWORD', 'BANKOPS_RECONCILIATION_PASSWORD',
             'BANKOPS_BANKING_API_TOKEN', 'BANKOPS_AGENT_API_TOKEN',
             'BANKOPS_GRAFANA_ADMIN_PASSWORD', 'BANKOPS_AIRFLOW_METADATA_ADMIN_PASSWORD',
             'BANKOPS_AIRFLOW_METADATA_PASSWORD', 'BANKOPS_AIRFLOW_UI_PASSWORD',
             'BANKOPS_AIRFLOW_VIEWER_PASSWORD', 'BANKOPS_AIRFLOW_JWT_SECRET',
             'BANKOPS_PROPOSER_TOKEN', 'BANKOPS_REVIEWER_TOKEN')
    values = {name: secrets.token_hex(32) for name in names}
    if prefix not in ('bankops-step67-', 'bankops-step68-', 'bankops-step69-'):
        raise ValueError('Unsupported isolated project prefix')
    values['BANKOPS_LOCAL_PROJECT'] = prefix + secrets.token_hex(6)
    for source, target in [('BANKOPS_AGENT_API_TOKEN', 'BANKOPS_AGENT_API_TOKEN_SHA256'),
                           ('BANKOPS_PROPOSER_TOKEN', 'BANKOPS_PROPOSER_SHA256'),
                           ('BANKOPS_REVIEWER_TOKEN', 'BANKOPS_REVIEWER_SHA256')]:
        values[target] = hashlib.sha256(values[source].encode()).hexdigest()
    secret_dir = root / '.secrets'
    secret_dir.mkdir(mode=0o700)
    token = secret_dir / 'banking-token'
    token.write_text(values['BANKOPS_BANKING_API_TOKEN'])
    # Prometheus runs as nobody; host access remains protected by the 0700 parent.
    token.chmod(0o444)
    with destination.open('x') as stream:
        stream.write(''.join(f'{key}={value}\n' for key, value in values.items()))
    destination.chmod(0o600)
    return values


def main():
    generate()
    print('Generated ignored local credentials and a unique isolated Compose project')


if __name__ == '__main__':
    main()
