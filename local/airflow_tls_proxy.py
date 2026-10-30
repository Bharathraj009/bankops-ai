"""Fixture-only TLS front door; fixed GET-only Airflow resource, no diagnostic logs."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import http.client
import ssl
import socket
import sys
import threading


class Health(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        try:
            context = ssl.create_default_context(cafile='/tls/cert.pem')
            with context.wrap_socket(socket.create_connection(('127.0.0.1', 8443), timeout=3),
                                     server_hostname='airflow-evidence'):
                pass
            self.send_response(200)
        except (OSError, ValueError):
            self.send_response(503)
        self.end_headers()


health = ThreadingHTTPServer(('127.0.0.1', 8000), Health)
if '--health-only' in sys.argv:
    health.serve_forever()
    raise SystemExit
threading.Thread(target=health.serve_forever, daemon=True).start()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if not self.path.startswith('/api/v2/dags/bankops_daily_reconciliation') or len(self.path) > 2048:
            self.send_error(404)
            return
        upstream = http.client.HTTPConnection('airflow', 8080, timeout=10)
        try:
            upstream.request('GET', self.path, headers={'Authorization': self.headers.get('Authorization', '')})
            response = upstream.getresponse()
            data = response.read(262145)
            if len(data) > 262144:
                self.send_error(502)
                return
            self.send_response(response.status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        finally:
            upstream.close()


server = ThreadingHTTPServer(('0.0.0.0', 8443), Handler)
context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain('/tls/cert.pem', '/tls/key.pem')
server.socket = context.wrap_socket(server.socket, server_side=True)
server.serve_forever()
