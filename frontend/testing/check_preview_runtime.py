"""Verify the built preview image against synthetic HTTP stubs, never banking data."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import subprocess
import threading
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]


def docker(*args, **kwargs):
    return subprocess.run(['docker', *args], check=True, text=True,
                          capture_output=True, **kwargs).stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', default='bankops-step71-remediation/frontend:local')
    args = parser.parse_args()
    if not args.image.startswith('bankops-step71-remediation/frontend:'):
        raise SystemExit('Use an explicit Step 71 remediation verification image')
    context = docker('context', 'show')
    endpoint = json.loads(docker('context', 'inspect', context))[0]['Endpoints']['docker']['Host']
    endpoint = os.environ.get('DOCKER_HOST', endpoint)
    if not endpoint.startswith(('npipe://', 'unix://')):
        raise SystemExit('Only local Docker endpoints are allowed')
    requests = []
    writes = []

    class Stub(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            requests.append((self.path, self.headers.get('Authorization')))
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"role":"OPERATOR","status":"ok"}')

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
            writes.append((self.path, self.headers.get('Authorization'),
                           self.headers.get('Idempotency-Key'), body))
            self.do_GET()

    server = ThreadingHTTPServer(('0.0.0.0', 0), Stub)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    name = 'bankops-step71b-preview-' + secrets.token_hex(6)
    token = secrets.token_hex(32)
    target = f'http://host.docker.internal:{server.server_port}'
    env = dict(os.environ, BANKOPS_BANKING_API_TARGET=target,
               BANKOPS_MONITORING_API_TARGET=target, BANKOPS_AGENT_API_TOKEN=token)
    created = False
    try:
        docker('run', '-d', '--rm', '--pull', 'never', '--name', name,
               '--label', 'bankops.step=71b', '-p', '127.0.0.1::5173',
               '-e', 'BANKOPS_BANKING_API_TARGET', '-e', 'BANKOPS_MONITORING_API_TARGET',
               '-e', 'BANKOPS_AGENT_API_TOKEN', args.image, env=env)
        created = True
        port = json.loads(docker('inspect', '--format', '{{json .NetworkSettings.Ports}}', name))['5173/tcp'][0]['HostPort']
        base = f'http://127.0.0.1:{port}'

        def get(path, headers=None, method='GET', body=None):
            request = urllib.request.Request(base + path, headers=headers or {}, method=method, data=body)
            try:
                with urllib.request.urlopen(request, timeout=5) as response:
                    return response.status, response.headers, response.read()
            except urllib.error.HTTPError as error:
                return error.code, error.headers, error.read()

        for _ in range(90):
            try:
                if get('/')[0] == 200:
                    break
            except (OSError, TimeoutError):
                pass
            time.sleep(1)
        else:
            raise AssertionError('Preview image did not become ready')
        assert get('/customer')[0] == 200
        assert get('/')[1]['X-Frame-Options'] == 'DENY'
        assert get('/api/v1/operator/me', {'Authorization': 'Bearer synthetic-operator'})[0] == 200
        assert requests[-1] == ('/api/v1/operator/me', 'Bearer synthetic-operator')
        for path in ('/monitoring-api/incidents/detect', '/reconciliation-api/incidents/detect'):
            assert get(path)[0] == 200
            assert requests[-1] == ('/incidents/detect', 'Bearer ' + token)
            assert get(path)[1]['Cache-Control'] == 'no-store'
        assert get('/customer-api/me', {'Authorization': 'Bearer synthetic-customer'})[0] == 200
        assert requests[-1] == ('/api/v1/customer/me', 'Bearer synthetic-customer')
        payload = b'{"synthetic":"stub-only"}'
        for route, upstream, key in [('/api/v1/transfers', '/api/v1/transfers', 'synthetic-operator'),
                                     ('/customer-api/transfers', '/api/v1/customer/transfers', 'synthetic-customer')]:
            assert get(route, {'Authorization': 'Bearer ' + key,
                              'Idempotency-Key': 'synthetic-idempotency-only',
                              'Content-Type': 'application/json'}, 'POST', payload)[0] == 200
            assert writes[-1] == (upstream, 'Bearer ' + key, 'synthetic-idempotency-only', payload)
        proposal = '/remediation/proposals/11111111-1111-4111-8111-111111111111'
        assert get('/governance-api' + proposal, {'Authorization': 'Bearer synthetic-reviewer'})[0] == 200
        assert requests[-1] == (proposal, 'Bearer synthetic-reviewer')
        count = len(requests)
        assert get('/api/v1/accounts', {'Origin': 'https://attacker.invalid'}, 'POST')[0] == 403
        assert get('/monitoring-api/incidents/detect', method='POST')[0] == 404
        assert get('/api/v1/unsupported')[0] == 404
        assert len(requests) == count
        docker('exec', name, 'node', '-e', "const f=require('node:fs'); for(const p of ['vitest','typescript','eslint','@playwright/test','@vitejs/plugin-react']) if(f.existsSync('/app/node_modules/'+p))process.exit(1); if(f.existsSync('/usr/local/lib/node_modules/npm'))process.exit(1)")
        print('PASS: built preview, SPA routes, proxy credentials, role separation, cross-origin/method denials, and no build/test/npm tooling')
    finally:
        if created:
            docker('stop', '--timeout', '30', name)
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()
