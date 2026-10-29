"""Print test counts only; provider exception bodies and properties may hold secrets."""
from pathlib import Path
import sys
import xml.etree.ElementTree as ET


def main():
    totals = dict.fromkeys(('tests', 'failures', 'errors', 'skipped'), 0)
    reports = list(Path(sys.argv[1]).glob('TEST-*.xml'))
    for report in reports:
        try:
            suite = ET.parse(report).getroot()
            for key in totals:
                totals[key] += int(suite.get(key, '0'))
        except (ET.ParseError, ValueError):
            print('An incomplete test report could not be summarized')
    print(f'Completed report files: {len(reports)}; totals: {totals}')
    print('Inspect the first failing workflow step; raw report contents are not uploaded')


if __name__ == '__main__':
    main()
