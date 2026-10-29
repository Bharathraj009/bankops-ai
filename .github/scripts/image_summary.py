"""Show severity totals without copying image environment/configuration into logs."""
from collections import Counter
import json
import os
from pathlib import Path
import sys


def summary(report):
    counts = Counter(v['Severity'] for result in report.get('Results', [])
                     for v in (result.get('Vulnerabilities') or []))
    return counts['HIGH'], counts['CRITICAL']


def main():
    path = Path(sys.argv[1])
    if not path.is_file():
        print('Scan did not complete; inspect the failed scanner step')
        return 1
    high, critical = summary(json.loads(path.read_text()))
    message = f'Image {os.environ["IMAGE"]}: HIGH={high}, CRITICAL={critical}. '
    message += 'See image-security artifacts for packages, installed/fixed versions and SBOM.\n'
    print(message, end='')
    with Path(os.environ['GITHUB_STEP_SUMMARY']).open('a', encoding='utf-8') as stream:
        stream.write(message)
    return 0


if __name__ == '__main__':
    sys.exit(main())
