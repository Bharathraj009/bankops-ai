"""Isolated real-Vite credential forwarding check. No banking/agent writes.

Generated keys stay in process memory/child environment. No browser artifacts,
credentials or real endpoints are used. Stops only its own child on completion.
"""
import json
import os
from pathlib import Path
import secrets
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import urllib.request
import urllib.error

ROOT=Path(__file__).resolve().parents[1]


def main():
    bank,agent,reviewer=(secrets.token_urlsafe(32) for _ in range(3))
    observations=[]
    class Stub(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            expected=bank if self.path.startswith('/api/v1/') else reviewer if self.path.startswith('/remediation/') else agent
            origin=self.headers.get('Origin')
            if self.path.startswith('/api/v1/customer/'):
                expected='cus_'+'x'*43
            observations.append(self.headers.get('Authorization')=='Bearer '+expected
                and (origin is None or origin=='http://'+self.headers.get('Host','')))
            body=b'{"status":"ok"}'
            self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)))
            self.end_headers();self.wfile.write(body)
    server=ThreadingHTTPServer(('127.0.0.1',18087),Stub)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    env={**os.environ,'BANKOPS_BANKING_API_TOKEN':bank,'BANKOPS_AGENT_API_TOKEN':agent,
        'BANKOPS_BANKING_API_TARGET':'http://127.0.0.1:18087','BANKOPS_MONITORING_API_TARGET':'http://127.0.0.1:18087',
        'BANKOPS_INVESTIGATION_API_TARGET':'http://127.0.0.1:18087','BANKOPS_GOVERNANCE_API_TARGET':'http://127.0.0.1:18087'}
    process=None
    try:
        process=subprocess.Popen(['node','node_modules/vite/bin/vite.js','--host','127.0.0.1','--port','5187','--strictPort'],
            cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        def get(path,headers=None):
            with opener.open(urllib.request.Request('http://127.0.0.1:5187'+path,headers=headers or {}),timeout=5) as response:
                return response.read()
        for attempt in range(40):
            try:get('/');break
            except OSError:
                if process.poll() is not None:raise RuntimeError('Isolated Vite startup failed') from None
                time.sleep(.25)
        else:raise RuntimeError('Isolated Vite startup timed out')
        # Caller must explicitly supply operator authority; the server key is not injected.
        get('/api/v1/accounts/11111111-1111-4111-8111-111111111111',{'Origin':'http://127.0.0.1:5187'})
        assert observations==[False]
        get('/api/v1/accounts/11111111-1111-4111-8111-111111111111',{'Authorization':'Bearer '+bank,'Origin':'http://127.0.0.1:5187'})
        get('/customer-api/me',{'Authorization':'Bearer cus_'+'x'*43})
        get('/monitoring-api/health')
        get('/governance-api/remediation/proposals/11111111-1111-4111-8111-111111111111',{'Authorization':'Bearer '+reviewer})
        assert observations==[False,True,True,True,True]
        # Config source, HTML and client code do not contain server-generated keys.
        for path in ['/','/src/main.tsx','/src/banking.ts','/src/governance.ts']:
            body=get(path)
            assert all(key.encode() not in body for key in (bank,agent,reviewer))
        print(json.dumps({'anonymous_banking_not_elevated':True,'customer_credential_preserved':True,'operator_credential_explicit':True,'agent_server_key_forwarded':True,
            'reviewer_credential_preserved':True,'same_origin_host_preserved':True,
            'keys_absent_from_client_sources':True,'real_banking_connections':0}))
    finally:
        if process is not None:
            process.terminate()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
        server.shutdown();server.server_close()


if __name__=='__main__':main()
