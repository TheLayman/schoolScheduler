from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from solver import generate_schedule_from_config

class handler(BaseHTTPRequestHandler):
    def _set_headers(self, content_type='application/json', status=200):
        self.send_response(status)
        self.send_header('Content-type', content_type)
        self.end_headers()
    
    def do_POST(self):
        if self.path == '/index':
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            try:
                config = json.loads(post_data)
                schedule = generate_schedule_from_config(config)
                if schedule is None:
                    self._set_headers(status=500)
                    response = {"error": "No solution found!"}
                else:
                    self._set_headers()
                    response = {"schedule": schedule}
            except Exception as e:
                self._set_headers(status=500)
                response = {"error": str(e)}
            self.wfile.write(json.dumps(response).encode('utf-8'))
        else:
            self.send_error(404)

    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write('GEORGE VENEEL DOGGA'.encode('utf-8'))

