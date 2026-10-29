"""One-command local operator. Never removes volumes/networks or changes daemon settings."""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import queue
import re
import runpy
import subprocess
import sys
import threading
import time
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
RUNTIME = ('postgres', 'banking', 'agent', 'frontend', 'airflow-metadata', 'airflow', 'prometheus', 'grafana', 'jaeger')
JOBS = ('prepare', 'migrate', 'grant')
PORTS = {'frontend': 15173, 'airflow': 18087, 'prometheus': 19097, 'grafana': 13007, 'jaeger': 16687}
FIXTURE_PORTS = {'frontend': 15269, 'airflow': 18069, 'prometheus': 19069, 'grafana': 13069, 'jaeger': 16669}


class LocalError(Exception):
    pass


def local_environment():
    # --env-file is authoritative; inherited service/provider settings must not leak
    # into a reproducible local stack or an image build.
    return {k: v for k, v in os.environ.items() if not k.startswith(
        ('BANKOPS_', 'SPRING_', 'OTEL_', 'VITE_', 'AIRFLOW__', 'GF_', 'COMPOSE_'))}


def local_endpoint(endpoint):
    parsed = urlparse(endpoint)
    return parsed.scheme in ('unix', 'npipe') or (parsed.scheme == 'tcp' and parsed.hostname in ('localhost', '127.0.0.1', '::1'))


def redact(text, values):
    for key, value in values.items():
        if key != 'BANKOPS_LOCAL_PROJECT' and value:
            text = text.replace(value, '[REDACTED]')
    return text


def select_subnets(pool, existing, count):
    try:
        network = ipaddress.ip_network(pool)
        private = [ipaddress.ip_network(s) for s in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')]
        if network.version != 4 or not any(network.subnet_of(n) for n in private) or not 16 <= network.prefixlen <= 24:
            raise ValueError()
        used = [ipaddress.ip_network(s) for s in existing if ':' not in s]
    except ValueError:
        raise LocalError('Network pool must be an RFC1918 IPv4 CIDR with prefix /16 through /24.') from None
    chosen = [str(s) for s in network.subnets(new_prefix=24) if not any(s.overlaps(u) for u in used)]
    if len(chosen) < count:
        raise LocalError('Not enough unused /24 subnets. For a NEW project choose --network-pool <private CIDR>; no networks were removed.')
    return chosen[:count]


def network_plan(config, networks, pool, previous=None):
    """Adopt existing declarations unchanged; allocate only absent project networks."""
    project = config['name']
    by_name = {n['Name']: n for n in networks}
    if previous:
        if previous['project'] != project:
            raise LocalError('Network plan belongs to another project; refusing to change retained networking.')
        if pool and pool != previous['pool']:
            raise LocalError('Network pool is already fixed for this project. Use its saved plan; changing existing networks requires separate authorization.')
        if set(previous['adopted']) | set(previous['overlay']['networks']) != set(config['networks']):
            raise LocalError('Network declarations changed. Review them separately; retained networks will not be recreated automatically.')
        for definition in config['networks'].values():
            actual = by_name.get(definition['name'])
            if actual and (actual.get('Labels') or {}).get('com.docker.compose.project') != project:
                raise LocalError('A retained network is owned by another project; refusing to modify it.')
        for key, definition in previous['overlay'].get('networks', {}).items():
            actual = by_name.get(config['networks'][key]['name'])
            wanted = definition['ipam']['config'][0]['subnet']
            if actual and wanted not in [c.get('Subnet') for c in ((actual.get('IPAM') or {}).get('Config') or [])]:
                raise LocalError('Existing network differs from the saved plan. Inspect it; no network will be changed automatically.')
        return previous
    used = [c['Subnet'] for n in networks for c in ((n.get('IPAM') or {}).get('Config') or []) if c.get('Subnet')]
    missing = []
    for key, definition in config['networks'].items():
        if definition.get('external'):
            raise LocalError('Unified local networks must not be external.')
        actual = by_name.get(definition['name'])
        if actual:
            if (actual.get('Labels') or {}).get('com.docker.compose.project') != project:
                raise LocalError('A network name is owned by another project; refusing to attach or modify it.')
        else:
            missing.append(key)
    pool = pool or '10.69.0.0/16'
    subnets = select_subnets(pool, used, len(missing))
    overlay = {'networks': {key: {'ipam': {'config': [{'subnet': subnet}]}} for key, subnet in zip(missing, subnets)}}
    return {'project': project, 'pool': pool, 'adopted': [k for k in config['networks'] if k not in missing], 'overlay': overlay}


def advice(output):
    lower = output.lower()
    if 'address already in use' in lower or 'port is already allocated' in lower:
        return 'A localhost port is occupied. Inspect `docker ps` and the runbook ports; do not stop an unrelated service automatically.'
    if 'fully subnetted' in lower or 'overlap' in lower:
        return 'Network allocation failed. Inspect saved IPAM and host/VPN routes; choose a free pool for a NEW project. Never prune retained networks.'
    if 'permission' in lower or 'daemon' in lower or 'pipe/docker' in lower:
        return 'Check Docker Desktop/daemon availability and Docker access permissions; respect the tool approval controls.'
    return 'Run `python local/platform.py health` and `python local/platform.py logs <service>`. Check prepare/migrate/grant first; never reset credentials or volumes to bypass an error.'


class Platform:
    def __init__(self, args):
        self.args = args
        self.state = ROOT if not args.fixture else ROOT / 'results' / ('step69-' + args.fixture)
        self.values = {}
        self.ports = FIXTURE_PORTS if args.fixture else PORTS
        self.state.mkdir(parents=True, exist_ok=True, mode=0o700)
        env_path = self.state / '.env.local'
        if not env_path.exists():
            if args.action != 'up':
                raise LocalError('Local configuration is missing. Run `python local/platform.py up` first (with the same --fixture if used).')
            self.values = runpy.run_path(str(ROOT / 'init.py'))['generate'](self.state, 'bankops-step69-' if args.fixture else 'bankops-step67-')
            print('Generated private local credentials; existing credentials are never replaced.', flush=True)
        else:
            self.values = dict(line.split('=', 1) for line in env_path.read_text().splitlines() if line and not line.startswith('#'))
        project = self.values.get('BANKOPS_LOCAL_PROJECT', '')
        if not re.fullmatch(r'bankops-step(67|69)-[0-9a-f]{12}', project):
            raise LocalError('Unexpected project name. Refusing to target arbitrary development or production infrastructure.')
        contexts = json.loads(self.run(['docker', 'context', 'inspect']))
        endpoint = contexts[0]['Endpoints']['docker']['Host']
        if os.environ.get('DOCKER_HOST') and not os.environ.get('DOCKER_CONTEXT'):
            endpoint = os.environ['DOCKER_HOST']
        if not local_endpoint(endpoint):
            raise LocalError('Only local Docker endpoints are supported. Select Docker Desktop/a local context; no remote services were started.')
        self.run(['docker', 'version', '--format', '{{.Server.Version}}'])
        version = self.run(['docker', 'compose', 'version', '--short'])
        match = re.search(r'(\d+)\.(\d+)\.(\d+)', version)
        if not match or tuple(map(int, match.groups())) < (2, 24, 4):
            raise LocalError('Docker Compose 2.24.4+ is required for the existing !override declarations.')
        self.base = ['docker', 'compose', '-p', project, '--env-file', str(env_path), '-f', str(ROOT / 'compose.yaml')]
        fixture_path = self.state / 'compose.json'
        if args.fixture and fixture_path.exists():
            saved = json.loads((self.state / 'network-plan.local.json').read_text())
            if args.network_pool and args.network_pool != saved['pool']:
                raise LocalError('The fixture network pool is already fixed; create a fresh fixture to use another pool.')
            self.compose = ['docker', 'compose', '-p', project, '-f', str(fixture_path)]
            self.config = json.loads(fixture_path.read_text())
            runpy.run_path(str(ROOT / 'recovery.py'))['validate_fixture'](self.config, project, prefix='bankops-step69-')
            network_plan(self.config, self.networks(), args.network_pool, saved)
            return
        config = json.loads(self.run(self.base + ['config', '--format', 'json']))
        networks = self.networks()
        plan_path = self.state / 'network-plan.local.json'
        previous = json.loads(plan_path.read_text()) if plan_path.exists() else None
        plan = network_plan(config, networks, args.network_pool, previous)
        self.write_private(plan_path, plan)
        if args.action == 'up':
            print(f"Networking: {len(plan['adopted'])} existing declarations preserved; {len(plan['overlay']['networks'])} explicit subnet declarations from {plan['pool']}.", flush=True)
        if args.fixture:
            source = json.loads(self.run(['docker', 'compose', '--env-file', str(ROOT / '.env.local'), '-f', str(ROOT / 'compose.yaml'), 'config', '--format', 'json']))
            for name, service in config['services'].items():
                if 'build' in service:
                    image = source['services'][name].get('image', source['name'] + '-' + name)
                    pinned = project + '-' + name + ':fixture'
                    self.run(['docker', 'image', 'tag', image, pinned])
                    service['image'] = pinned
                    service['pull_policy'] = 'never'
                    del service['build']
                for port in service.get('ports', []):
                    port['published'] = str(self.ports[name])
            for mount in config['services']['prometheus']['volumes']:
                if mount.get('target') == '/run/secrets/banking-token':
                    mount['source'] = str(self.state / '.secrets/banking-token')
            for key, definition in plan['overlay']['networks'].items():
                config['networks'][key].update(definition)
            runpy.run_path(str(ROOT / 'recovery.py'))['validate_fixture'](config, project, prefix='bankops-step69-')
            self.write_private(fixture_path, config)
            self.compose = ['docker', 'compose', '-p', project, '-f', str(fixture_path)]
        else:
            overlay = self.state / 'networks.local.json'
            self.write_private(overlay, plan['overlay'])
            self.compose = self.base + ['-f', str(overlay)]
            config = json.loads(self.run(self.compose + ['config', '--format', 'json']))
        self.config = config

    def networks(self):
        ids = self.run(['docker', 'network', 'ls', '-q']).split()
        return json.loads(self.run(['docker', 'network', 'inspect', *ids])) if ids else []

    @staticmethod
    def write_private(path, value):
        path.write_text(json.dumps(value, indent=2) + '\n')
        path.chmod(0o600)

    def run(self, command, log=None, show=False, timeout=900):
        """Drain output continuously, redact before writing logs, keep true exit status."""
        process = subprocess.Popen(command, cwd=REPO, env=local_environment(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
        lines = queue.Queue()
        def read():
            for line in process.stdout:
                lines.put(line)
            lines.put(None)
        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        output = []
        started = heartbeat = time.monotonic()
        stream = None
        if log:
            folder = self.state / 'results'
            folder.mkdir(exist_ok=True, mode=0o700)
            stream = (folder / log).open('w', encoding='utf-8')
            (folder / log).chmod(0o600)
        try:
            while True:
                if time.monotonic() - started > timeout:
                    process.terminate()
                    process.wait(timeout=20)
                    raise LocalError('Command timed out. Inspect health/logs; containers and volumes were preserved.')
                try:
                    line = lines.get(timeout=1)
                except queue.Empty:
                    if log and time.monotonic() - heartbeat > 20:
                        print('Still waiting for Docker/health checks; volumes and credentials are preserved.', flush=True)
                        heartbeat = time.monotonic()
                    continue
                if line is None:
                    break
                output.append(line)
                safe = redact(line, self.values)
                if stream:
                    stream.write(safe)
                    stream.flush()
                if show:
                    encoding = sys.stdout.encoding or 'utf-8'
                    print(safe.encode(encoding, errors='replace').decode(encoding), end='', flush=True)
            status = process.wait(timeout=20)
            text = ''.join(output)
            if status:
                safe = redact(''.join(output[-12:]), self.values)
                raise LocalError(f'Docker command failed (exit {status}).\n{safe}\n{advice(safe)}')
            return text
        finally:
            if stream:
                stream.close()
            process.stdout.close()

    def dc(self, *args, **kwargs):
        return self.run(self.compose + list(args), **kwargs)

    def states(self):
        return {v['Service']: v for line in self.dc('ps', '-a', '--format', 'json').splitlines() if line.strip() for v in [json.loads(line)]}

    def health(self):
        states = self.states()
        for name in (*RUNTIME, *JOBS):
            item = states.get(name, {})
            print(f"{name:18} {item.get('State', 'missing'):9} {item.get('Health') or ('exit '+str(item.get('ExitCode')) if item.get('State')=='exited' else '')}")
        good = all(states.get(name, {}).get('Health') == 'healthy' and states[name]['State'] == 'running' for name in RUNTIME)
        good = good and all(states.get(name, {}).get('State') == 'exited' and states[name]['ExitCode'] == 0 for name in JOBS)
        return good

    def up(self):
        self.dc('config', '--quiet')
        missing = []
        for name, service in self.config['services'].items():
            if 'build' in service:
                image = service.get('image', self.config['name'] + '-' + name)
                result = subprocess.run(['docker', 'image', 'inspect', image], capture_output=True)
                if result.returncode:
                    missing.append(name)
        if missing:
            print('Building only missing images: ' + ', '.join(missing), flush=True)
            self.dc('build', *missing, log='build.log')
        else:
            print('Required local images are available; no rebuild requested.', flush=True)
        print('Starting nine runtimes; database prepare -> migrate/validate -> grant -> runtime remains health-gated.', flush=True)
        try:
            self.dc('up', '-d', '--no-build', '--wait', '--wait-timeout', '600', log='startup.log')
        except LocalError:
            self.health()
            raise
        if not self.health():
            raise LocalError('Startup returned but required services/jobs are not healthy. Inspect the listed service logs.')
        self.access()

    def access(self):
        for name, port in self.ports.items():
            print(f'{name:12} http://127.0.0.1:{port}')
        print('Customer APIs, inference and remediation remain disabled. Secrets stay in the ignored .env.local file.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--network-pool', default=os.environ.get('BANKOPS_LOCAL_NETWORK_POOL'), help='Private /16 through /24 range for NEW networks; default 10.69.0.0/16')
    parser.add_argument('--fixture', help='Disposable verification state ID: exactly 12 hex characters; separate ports/volumes')
    parser.add_argument('action', choices=['up', 'health', 'logs', 'stop', 'restart', 'build', 'verify', 'test'])
    parser.add_argument('services', nargs='*')
    parser.add_argument('--recovery', action='store_true', help='test only: execute Step 68 disposable recovery suite')
    args = parser.parse_args()
    if args.fixture and not re.fullmatch('[0-9a-f]{12}', args.fixture):
        parser.error('--fixture requires a 12-character hexadecimal ID, not a path or project name')
    if any(s not in RUNTIME + JOBS for s in args.services):
        parser.error('Unknown service; use names shown by health')
    if args.services and args.action not in ('logs', 'restart', 'build'):
        parser.error('Service names apply only to logs, restart, or build')
    if args.action == 'restart' and any(s in JOBS for s in args.services):
        parser.error('Migration/ACL jobs are sequenced by up, not independently restarted')
    try:
        platform = Platform(args)
        if args.action == 'up':
            platform.up()
        elif args.action == 'health':
            if not platform.health():
                raise LocalError('Platform is not fully healthy. Start stopped services with up; inspect failed services/jobs with logs.')
        elif args.action == 'logs':
            platform.dc('logs', '--tail', '100', *args.services, show=True)
        elif args.action == 'stop':
            platform.dc('stop', '--timeout', '30', log='stop.log')
            print('Stopped safely. Containers, networks and all volumes are preserved.')
        elif args.action == 'restart':
            if args.services:
                platform.dc('restart', '--timeout', '30', *args.services, log='restart.log')
                platform.dc('up', '-d', '--no-build', '--no-recreate', '--no-deps', '--wait', '--wait-timeout', '600', *args.services, log='restart-health.log')
            else:
                platform.dc('stop', '--timeout', '30', log='stop.log')
                platform.up()
        elif args.action == 'build':
            if args.fixture:
                raise LocalError('Disposable fixtures use frozen built image IDs. Build the ordinary local images, then create a fresh fixture.')
            platform.dc('build', *args.services, log='build.log', show=True)
        elif args.action == 'verify':
            verify = runpy.run_path(str(ROOT / 'verify.py'))['main']
            port_map = {PORTS[key]: value for key, value in platform.ports.items()}
            verify(state=platform.state, compose=platform.compose, ports=port_map, emit=False)
            print('Verified frontend/banking/agent routes, Prometheus, Grafana, Jaeger and SELECT-only Airflow reconciliation.')
        elif args.action == 'test':
            if args.recovery:
                command = [sys.executable, str(ROOT / 'recovery.py')]
            else:
                python = REPO / ('agent/.venv/Scripts/python.exe' if os.name == 'nt' else 'agent/.venv/bin/python')
                if not python.exists():
                    raise LocalError('Developer tests need the project agent venv with pytest and frontend Playwright dependencies. Verification itself uses only Python stdlib + Docker.')
                command = [str(python), '-m', 'pytest', 'local/tests', 'security/tests', '-q', '-W', 'error']
            platform.run(command, log='tests.log', show=True)
    except (LocalError, OSError, ValueError, AssertionError, subprocess.TimeoutExpired) as error:
        values = platform.values if 'platform' in locals() else {}
        print(redact(f'Local platform error: {error}', values), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
