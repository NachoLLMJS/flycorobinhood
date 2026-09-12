"""Servidor local: python server.py. Solo expone public/."""
import json
import mimetypes
import os
import sys
import time
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, unquote, parse_qs
import backend


class QuietThreadingHTTPServer(ThreadingHTTPServer):
    """Ignore routine browser disconnects without hiding real server errors."""
    def handle_error(self, request, client_address):
        if sys.exc_info()[0] in (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return
        super().handle_error(request, client_address)


def make_server(app, public, port=4775, bind_host='127.0.0.1', public_mode=None):
    public = Path(public).resolve()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def respond(self, status, data, content_type='application/json; charset=utf-8'):
            if not isinstance(data, bytes):
                data = json.dumps(data, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(data)

        def trusted(self):
            host = self.headers.get('Host', '')
            if len(self.headers.get_all('Host', [])) != 1 or not host or any(c in host for c in ('/', '\\', '\x00')):
                return False
            if not self.server.public_mode:
                local_hosts = {'127.0.0.1:' + str(self.server.server_port), 'localhost:' + str(self.server.server_port)}
                if host not in local_hosts:
                    return False
            origins = self.headers.get_all('Origin', [])
            return len(origins) <= 1 and (not origins or origins[0] in ('http://' + host, 'https://' + host)) and self.headers.get('Sec-Fetch-Site', '') not in ('cross-site', 'same-site')

        def do_POST(self):
            self.connection.settimeout(15)
            if self.server.public_mode:
                return self.respond(403, {'error':'Public deployment is read-only'})
            if not self.trusted():
                return self.respond(403, {'error':'Origin or Host is not allowed'})
            if self.headers.get('Content-Type', '').split(';')[0].strip().lower() != 'application/json':
                return self.respond(415, {'error':'application/json is required'})
            if self.headers.get('Transfer-Encoding') or len(self.headers.get_all('Content-Length', [])) != 1:
                return self.respond(400, {'error':'Only one Content-Length header is required'})
            try:
                size = int(self.headers['Content-Length'])
            except ValueError:
                return self.respond(400, {'error':'Invalid length'})
            if size < 0 or size > 16384:
                return self.respond(413, {'error':'Request body is too large'})
            try:
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise ValueError('A JSON object is required')
                path = urlsplit(self.path).path
                if path == '/api/scheduler':
                    return self.respond(200, app.set_scheduler(data.get('enabled')))
                if path == '/api/research':
                    return self.respond(200, app.research())
                if path == '/api/meeting':
                    return self.respond(202, app.start_meeting())
                if path.startswith('/api/proposals/') and path.endswith('/approve'):
                    try:
                        return self.respond(200, app.approve(path.split('/')[3]))
                    except KeyError:
                        return self.respond(404, {'error':'Proposal not found'})
                return self.respond(404, {'error':'Unknown route'})
            except (ValueError, UnicodeError):
                return self.respond(400, {'error':'Invalid JSON or parameters'})
            except backend.Busy as exc:
                return self.respond(409, {'error':str(exc)})
            except backend.Blocked as exc:
                return self.respond(503, {'error':str(exc), 'provider':app.provider.state()})
            except TimeoutError:
                return self.respond(408, {'error':'Request read timed out'})
            except Exception:
                return self.respond(500, {'error':'Internal error; no transaction was executed'})

        def do_GET(self):
            split = urlsplit(self.path)
            path = unquote(split.path)
            if path == '/api/health':
                return self.respond(200, {'ok': True, 'service': 'flyco-robinhood'})
            if path == '/api/config':
                return self.respond(200, {'xProfileUrl': os.environ.get('FLYCOROBINHOOD_PUBLIC_X_PROFILE_URL', '').strip()})
            if path == '/api/state':
                state = app.state()
                state['publicReadOnly'] = self.server.public_mode
                return self.respond(200, state)
            if path == '/api/events':
                try:
                    after = max(0, int(parse_qs(split.query).get('after', ['0'])[0]))
                except ValueError:
                    return self.respond(400, {'error':'Invalid event cursor'})
                once = parse_qs(split.query).get('once', ['0'])[0] == '1'
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
                self.send_header('Cache-Control', 'no-cache, no-store')
                self.send_header('Connection', 'keep-alive')
                self.send_header('X-Accel-Buffering', 'no')
                self.end_headers()
                deadline = time.monotonic() + (5 if once else 60)
                try:
                    while time.monotonic() < deadline:
                        events = app.events_after(after)
                        if events:
                            for event in events:
                                self.wfile.write(('id: ' + str(event['id']) + '\n').encode())
                                self.wfile.write(('event: ' + event['type'] + '\n').encode())
                                self.wfile.write(('data: ' + json.dumps(event['payload'], ensure_ascii=False) + '\n\n').encode('utf-8'))
                                after = event['id']
                            self.wfile.flush()
                            if once:
                                self.close_connection = True
                                return
                        else:
                            self.wfile.write(b': keepalive\n\n')
                            self.wfile.flush()
                            time.sleep(1)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    return
                return
            if any(c in path for c in ('\\', ':', '\x00')) or any(part.startswith('.') for part in path.split('/') if part):
                return self.respond(403, {'error':'Path is not allowed'})
            target = (public / ('index.html' if path == '/' else path.lstrip('/'))).resolve()
            if not target.is_relative_to(public) or target.suffix.lower() not in {'.html','.css','.js','.json','.svg','.png','.jpg','.jpeg','.webp','.ico','.glb','.gltf','.bin','.woff','.woff2','.mp3','.ogg','.txt'}:
                return self.respond(403, {'error':'Path is not allowed'})
            if not target.is_file():
                return self.respond(404, {'error':'Not found'})
            return self.respond(200, target.read_bytes(), mimetypes.guess_type(target.name)[0] or 'application/octet-stream')

    httpd = QuietThreadingHTTPServer((bind_host, port), Handler)
    httpd.public_mode = bind_host not in ('127.0.0.1', 'localhost') if public_mode is None else bool(public_mode)
    return httpd


def main():
    import os
    import threading
    root = Path(__file__).resolve().parent
    role = os.environ.get('FLY_ROLE', 'web' if os.environ.get('PORT') else 'local')
    if role == 'web' or os.environ.get('LLM_API_KEY'):
        provider = backend.Provider(os.environ)
    else:
        from local_provider import HermesProvider
        provider = HermesProvider()
        threading.Thread(target=provider.verify, daemon=True).start()
    app = backend.App(root / 'data' / 'company.sqlite3', provider)
    stop = threading.Event()
    if role in ('local', 'worker'):
        threading.Thread(target=app.scheduler_loop, args=(stop,), daemon=True).start()
    bind_host = os.environ.get('HOST', '0.0.0.0' if os.environ.get('PORT') else '127.0.0.1')
    port = int(os.environ.get('PORT', '4775'))
    httpd = make_server(app, root/'public', port=port, bind_host=bind_host, public_mode=(role == 'web' or bool(os.environ.get('PORT'))))
    display_host = '127.0.0.1' if bind_host == '127.0.0.1' else bind_host
    print(f'FlyCo Robinhood: http://{display_host}:{port} | Ctrl+C to stop', flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        httpd.server_close()

if __name__ == '__main__':
    main()
