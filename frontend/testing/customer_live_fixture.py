"""Explicitly opt-in isolated Step 64 browser fixture, never development banking.

Starts only the packaged Spring app and Vite. Credentials are generated locally
and written only to an ignored synthetic-test manifest; never printed. Ctrl+C
stops the child processes and removes only that generated manifest.
"""
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
import urllib.request
import uuid

ROOT=Path(__file__).resolve().parents[2]
CACHE=ROOT/'frontend/.cache/step64'


def main():
    if os.environ.get('BANKOPS_ISOLATED_CUSTOMER')!='step64-local-only':
        raise SystemExit('Explicit isolated customer verification opt-in required')
    CACHE.mkdir(parents=True,exist_ok=True)
    manifest=CACHE/'session.json'
    if manifest.exists():raise SystemExit('Inspect the existing fixture manifest before starting another fixture')
    operator=secrets.token_urlsafe(40);reserve=str(uuid.uuid4());schema='customer_ui_'+uuid.uuid4().hex
    env={**{k:v for k,v in os.environ.items() if not k.startswith(('SPRING_','BANKOPS_'))},'BANKOPS_DB_USER':'bankops_test','BANKOPS_DB_PASSWORD':'isolated_step64_only',
        'BANKOPS_BANKING_API_TOKEN':operator,'BANKOPS_CUSTOMER_ENABLED':'true',
        'BANKOPS_DEV_FUNDING_ACCOUNT_ID':reserve,'BANKOPS_DEV_RESERVE_BOOTSTRAP_ENABLED':'true',
        'BANKOPS_DEV_RESERVE_INITIAL_BALANCE':'10000.00',
        'BANKOPS_BANKING_API_TARGET':'http://127.0.0.1:18064'}
    command=['C:/Program Files/Java/jdk-25/bin/java.exe','-jar',str(ROOT/'backend/banking-service/target/banking-service-0.0.1-SNAPSHOT.jar'),
        '--spring.profiles.active=dev','--server.port=18064',
        # Explicit administrator exception for this opt-in, test-only schema fixture.
        '--spring.flyway.enabled=true','--bankops.database.verify-runtime=false',
        '--spring.datasource.url=jdbc:postgresql://localhost:55464/bankops_test',
        '--spring.flyway.url=jdbc:postgresql://localhost:55464/bankops_test',
        '--spring.flyway.user=bankops_test','--spring.flyway.password=isolated_step64_only',
        '--spring.datasource.hikari.schema='+schema,'--spring.flyway.default-schema='+schema,'--spring.flyway.schemas='+schema]
    children=[];logs=[]
    try:
        for name,cmd,cwd in [('banking',command,ROOT),('vite',['node','node_modules/vite/bin/vite.js','--host','127.0.0.1','--port','5184','--strictPort'],ROOT/'frontend')]:
            log=(CACHE/(name+'.log')).open('w');logs.append(log)
            children.append(subprocess.Popen(cmd,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0))
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for attempt in range(120):
            if any(p.poll() is not None for p in children):raise RuntimeError('Isolated fixture startup failed; inspect private local logs')
            try:
                with opener.open('http://127.0.0.1:18064/actuator/health',timeout=2) as r:
                    if json.load(r)['status']=='UP':break
            except OSError:pass
            time.sleep(.5)
        else:raise RuntimeError('Isolated banking readiness timed out')
        manifest.write_text(json.dumps({'schema':schema,'operator':operator,'reserve':reserve}))
        manifest.chmod(0o600)
        print('Isolated customer fixture ready: banking 18064, frontend 5184; no development database connected.',flush=True)
        while all(p.poll() is None for p in children) and not (CACHE/'stop-request').exists():time.sleep(.5)
    finally:
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
                try:child.wait(timeout=15)
                except subprocess.TimeoutExpired:child.kill();child.wait(timeout=5)
        for log in logs:log.close()
        if manifest.exists():manifest.unlink()
        if (CACHE/'stop-request').exists():(CACHE/'stop-request').unlink()


if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:pass
