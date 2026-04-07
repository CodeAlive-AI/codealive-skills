"""Test helpers for CodeAlive skills runtime tests."""

from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer


@contextmanager
def mock_codealive_server(routes):
    """Start a local mock HTTP server.

    ``routes`` maps ``(method, path)`` to either:
    - ``(status_code, payload)``, where payload is JSON-serializable
    - a callable ``handler(request_info) -> (status_code, payload, headers)``
    """

    requests = []

    class Handler(BaseHTTPRequestHandler):
        def _handle(self, method: str):
            request_info = {
                "method": method,
                "path": self.path,
                "headers": {k: v for k, v in self.headers.items()},
                "body": self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode("utf-8")
                if method in {"POST", "PUT", "PATCH"}
                else "",
            }
            requests.append(request_info)

            route = routes.get((method, self.path))
            if route is None:
                self.send_response(404)
                self.end_headers()
                return

            if callable(route):
                status, payload, headers = route(request_info)
            else:
                status, payload = route
                headers = {}

            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self._handle("GET")

        def do_POST(self):
            self._handle("POST")

        def log_message(self, format, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", requests
    finally:
        server.shutdown()
        thread.join(timeout=1)
