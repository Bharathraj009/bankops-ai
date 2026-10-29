"""Remove installer/vendored tooling from the immutable production image only."""
from pathlib import Path
import shutil

if not (Path('/home/airflow/.local/lib/python3.12/site-packages').is_dir()
        or Path('/opt/venv/lib/python3.12/site-packages/airflow').is_dir()):
    raise SystemExit('Run only inside the Airflow image build')

for directory in (Path('/usr/local/lib/python3.12/site-packages'),
                  Path('/opt/venv/lib/python3.12/site-packages'),
                  Path('/home/airflow/.local/lib/python3.12/site-packages')):
    for pattern in ('pip', 'pip-*.dist-info', 'setuptools', 'setuptools-*.dist-info',
                    'pkg_resources', '_distutils_hack', 'wheel', 'wheel-*.dist-info',
                    'uv', 'uv-*.dist-info', 'distutils-precedence.pth'):
        for target in directory.glob(pattern):
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
for directory in (Path('/usr/local/bin'), Path('/home/airflow/.local/bin'), Path('/opt/venv/bin')):
    for name in ('pip', 'pip3', 'pip3.12', 'wheel', 'uv', 'uvx', 'prek'):
        (directory / name).unlink(missing_ok=True)
