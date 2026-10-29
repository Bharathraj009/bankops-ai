"""Host/origin and deployment authentication boundary; no financial operations."""
import hashlib
import hmac
from urllib.parse import urlsplit
from starlette.responses import JSONResponse


class SecurityBoundary:
    def __init__(self, app, settings):
        self.app, self.settings = app, settings

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = scope.get('headers', [])
        values = lambda name: [v.decode('latin-1') for k, v in headers if k.lower() == name]
        hosts, origins = values(b'host'), values(b'origin')
        status = None
        try:
            hostname = urlsplit('http://' + hosts[0]).hostname if len(hosts) == 1 else None
            if hostname not in self.settings.allowed_hosts:
                status = 403
            if len(origins) > 1 or 'cross-site' in values(b'sec-fetch-site'):
                status = 403
            if origins:
                origin = urlsplit(origins[0])
                if (origin.scheme not in ('http', 'https') or origin.netloc.lower() != hosts[0].lower()
                    or origin.username is not None or origin.path or origin.query or origin.fragment):
                    status = 403
        except (ValueError, IndexError):
            status = 403
        path = scope.get('path', '')
        # These routes retain their independent proposer/reviewer authorization.
        role_route = path == '/remediation/proposals' or path.startswith('/remediation/proposals/')
        public_health = path == '/health' and scope['method'] == 'GET'
        required = (self.settings.environment == 'production' or not self.settings.host.is_loopback
                    or self.settings.api_token_sha256 is not None)
        if status is None and required and not public_health and not role_route:
            digest = self.settings.api_token_sha256
            auth = values(b'authorization')
            if digest is None:
                status = 503
            elif (len(auth) != 1 or not auth[0].startswith('Bearer ') or not 32 <= len(auth[0][7:]) <= 256
                  or not hmac.compare_digest(hashlib.sha256(auth[0][7:].encode()).hexdigest(), digest.get_secret_value())):
                status = 401

        async def secured_send(message):
            if message['type'] == 'http.response.start':
                names = {b'cache-control', b'x-content-type-options', b'x-frame-options', b'referrer-policy'}
                message = {**message, 'headers': [(k,v) for k,v in message.get('headers', []) if k.lower() not in names] +
                    [(b'cache-control', b'no-store'), (b'x-content-type-options', b'nosniff'),
                     (b'x-frame-options', b'DENY'), (b'referrer-policy', b'no-referrer')]}
            await send(message)
        if status is not None:
            return await JSONResponse({'detail': 'Request unavailable'}, status_code=status,
                headers={'WWW-Authenticate': 'Bearer'} if status == 401 else None)(scope, receive, secured_send)
        await self.app(scope, receive, secured_send)
