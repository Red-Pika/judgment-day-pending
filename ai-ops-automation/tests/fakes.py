"""Local stand-ins for Telegram/Slack (HTTP) and an SMTP server (real SMTP protocol, no TLS)."""
import json
import socketserver
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeHTTP:
    def __init__(self, status=200, body=b'{"ok":true}'):
        self.requests, self.status, self.body = [], status, body
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                outer.requests.append({"path": self.path, "body": json.loads(self.rfile.read(n) or b"{}")})
                self.send_response(outer.status)
                self.send_header("Content-Length", str(len(outer.body)))
                self.end_headers()
                self.wfile.write(outer.body)

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, kwargs={'poll_interval': 0.02}, daemon=True).start()

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


class FakeSMTP:
    def __init__(self):
        self.messages = []
        outer = self

        class H(socketserver.StreamRequestHandler):
            def handle(self):
                def w(s):
                    self.wfile.write(s.encode() + b"\r\n")
                    self.wfile.flush()
                w("220 fake ESMTP")
                rcpts = []
                while True:
                    line = self.rfile.readline()
                    if not line:
                        return
                    cmd = line.decode().strip()
                    up = cmd.upper()
                    if up.startswith(("EHLO", "HELO")):
                        w("250 fake")
                    elif up.startswith("RCPT"):
                        rcpts.append(cmd.split(":", 1)[1].strip().strip("<>"))
                        w("250 ok")
                    elif up == "DATA":
                        w("354 go")
                        data = []
                        while True:
                            l = self.rfile.readline()
                            if l in (b".\r\n", b""):
                                break
                            data.append(l)
                        outer.messages.append({"rcpts": rcpts, "data": b"".join(data).decode()})
                        rcpts = []
                        w("250 queued")
                    elif up == "QUIT":
                        w("221 bye")
                        return
                    else:
                        w("250 ok")

        class S(socketserver.ThreadingTCPServer):
            allow_reuse_address = True
            daemon_threads = True

        self.srv = S(("127.0.0.1", 0), H)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, kwargs={'poll_interval': 0.02}, daemon=True).start()

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()
