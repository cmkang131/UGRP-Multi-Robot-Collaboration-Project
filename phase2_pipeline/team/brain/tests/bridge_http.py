"""Exercise the planner CLI and its real HTTP handler with a supplied model stub."""
import io
import json
import sys
import threading
from http.client import HTTPResponse
from types import SimpleNamespace
from unittest import mock
from urllib.request import Request, urlopen


class BridgeHTTP:
    def __init__(self, module, args, log_dir, model):
        listen = module.HTTPServer
        self.server = None

        def capture(address, handler):
            self.handler = handler
            try:
                self.server = listen(address, handler)
            except PermissionError:
                # Sandboxes can deny even loopback. Feed the same HTTP request bytes to the handler in memory.
                pass
            return SimpleNamespace(serve_forever=lambda: None)

        argv = ["brain_server.py", *args, "--port", "0", "--log-dir", str(log_dir)]
        with mock.patch.object(module, "RealLLM", return_value=model), mock.patch.object(module, "HTTPServer", capture), mock.patch.object(sys, "argv", argv):
            module.main()
        if self.server is not None:
            self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
            self.thread.start()

    def close(self):
        if self.server is not None:
            self.server.shutdown()
            self.thread.join()
            self.server.server_close()

    def post(self, path, body):
        data = json.dumps(body).encode()
        if self.server is not None:
            url = "http://127.0.0.1:%d%s" % (self.server.server_port, path)
            with urlopen(Request(url, data=data, headers={"Content-Type": "application/json"}), timeout=20) as response:
                return json.load(response)
        headers = f"POST {path} HTTP/1.0\r\nContent-Type: application/json\r\nContent-Length: {len(data)}\r\n\r\n"
        handler = self.handler.__new__(self.handler)
        handler.rfile, handler.wfile = io.BytesIO(headers.encode() + data), io.BytesIO()
        handler.client_address = ("127.0.0.1", 0)
        handler.handle()
        wire = handler.wfile.getvalue()
        with HTTPResponse(SimpleNamespace(makefile=lambda *args: io.BytesIO(wire))) as response:
            response.begin()
            if response.status != 200:
                raise RuntimeError(f"{path} returned HTTP {response.status}")
            return json.load(response)
