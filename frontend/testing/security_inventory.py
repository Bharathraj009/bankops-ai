"""Read-only tracked-secret scan and public-package OSV advisory lookup.

Never prints matched values or transmits source code/credentials. Advisory requests
contain only public package coordinates. Output stays under ignored .cache/step63.
"""
import io
import json
from pathlib import Path
import re
import subprocess
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'frontend' / '.cache' / 'step63'
OUT.mkdir(parents=True, exist_ok=True)


def inventory(image_name):
    packages = []
    for lock in ['agent/requirements.lock', 'airflow/requirements.txt', 'airflow/requirements-airflow.txt']:
        for line in (ROOT/lock).read_text().splitlines():
            match=re.fullmatch(r'([\w.-]+)(?:\[[\w,]+\])?==([^\s]+)',line.strip())
            if match: packages.append((lock,'PyPI',match[1],match[2]))
    app=ROOT/'backend/banking-service/target/banking-service-0.0.1-SNAPSHOT.jar'
    with zipfile.ZipFile(app) as archive:
        for name in archive.namelist():
            if not name.startswith('BOOT-INF/lib/') or not name.endswith('.jar'): continue
            with zipfile.ZipFile(io.BytesIO(archive.read(name))) as lib:
                for path in lib.namelist():
                    if path.startswith('META-INF/maven/') and path.endswith('/pom.properties'):
                        props=dict(line.split('=',1) for line in lib.read(path).decode().splitlines() if '=' in line and not line.startswith('#'))
                        if all(key in props for key in ('groupId','artifactId','version')):
                            packages.append(('banking packaged JAR','Maven',props['groupId']+':'+props['artifactId'],props['version']))
    image = subprocess.run(['docker','run','--rm','--network','none','--entrypoint','python',
        image_name,'-m','pip','list','--format=json'], capture_output=True, text=True)
    if image.returncode == 0:
        for item in json.loads(image.stdout): packages.append(('Airflow runtime image','PyPI',item['name'],item['version']))
    return sorted(set(packages))


def scan():
    patterns={
        'private_key':re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
        'cloud_key':re.compile(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
        'provider_key':re.compile(r'\b(?:gsk_[A-Za-z0-9]{30,}|sk-proj-[A-Za-z0-9_-]{30,}|ghp_[A-Za-z0-9]{30,})\b'),
        'credential_literal_review':re.compile(r'''(?i)(?:password|api_key|api_token|secret)\s*[:=]\s*["']([^"'\s]{20,})["']'''),
    }
    findings=[]
    tracked=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=ROOT).decode().split('\0')
    for name in tracked:
        path=ROOT/name
        if not name or not path.is_file() or path.stat().st_size>2000000: continue
        try: lines=path.read_text(encoding='utf-8').splitlines()
        except (UnicodeError,OSError): continue
        for number,line in enumerate(lines,1):
            for category,pattern in patterns.items():
                if pattern.search(line):findings.append({'file':name,'line':number,'category':category})
    (OUT/'secret-scan.json').write_text(json.dumps({'findings':findings,
        'tracked_env_files':[p for p in tracked if Path(p).name in ('.env','.env.local')]},indent=2))
    print(json.dumps({'secret_candidate_count':len(findings),'categories':sorted({f['category'] for f in findings})}))


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--patched',action='store_true')
    args=parser.parse_args()
    scan()
    packages=inventory('bankops-airflow-step63-security:latest' if args.patched else 'bankops-airflow-airflow:latest')
    queries=[{'package':{'ecosystem':eco,'name':name},'version':version} for _,eco,name,version in packages]
    body=json.dumps({'queries':queries}).encode()
    request=urllib.request.Request('https://api.osv.dev/v1/querybatch',data=body,headers={'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(request,timeout=60) as response: result=json.load(response)
        affected=[{'source':src,'ecosystem':eco,'package':name,'version':version,'advisories':row.get('vulns',[])}
            for (src,eco,name,version),row in zip(packages,result['results'],strict=True) if row.get('vulns')]
        report={'queried':len(queries),'affected':affected,'airflow_runtime_included':any(p[0]=='Airflow runtime image' for p in packages)}
        (OUT/('osv-after.json' if args.patched else 'osv.json')).write_text(json.dumps(report,indent=2))
        print(json.dumps({'osv_packages_queried':len(queries),'affected_packages':len(affected),'airflow_runtime_included':report['airflow_runtime_included']}))
    except Exception as error:
        print(json.dumps({'advisory_lookup':'unavailable','error_type':type(error).__name__}))
        raise SystemExit(2) from None
