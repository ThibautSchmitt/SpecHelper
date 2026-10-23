"""Trusted sandbox bootstrap: bounded local TCP relay to the selected Unix broker."""

import os
import resource
import selectors
import socket
import socketserver
import sys
import threading


class Bridge(socketserver.BaseRequestHandler):
    def handle(self):
        upstream = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            upstream.connect("/broker.sock")
            with selectors.DefaultSelector() as selector:
                selector.register(self.request, selectors.EVENT_READ, upstream)
                selector.register(upstream, selectors.EVENT_READ, self.request)
                while True:
                    events = selector.select(20)
                    if not events:
                        return
                    for event, _ in events:
                        chunk = event.fileobj.recv(65536)
                        if not chunk:
                            return
                        event.data.sendall(chunk)
        finally:
            upstream.close()


class Server(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 16


if __name__ == "__main__":
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024 * 1024, 64 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
    resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
    resource.setrlimit(resource.RLIMIT_CPU, (285, 290))
    if os.getuid() != 10001 or os.getgid() != 10001:
        raise SystemExit("Analysis identity isolation unavailable")
    server = Server(("127.0.0.1", 8090), Bridge)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    process = os.spawnvp(os.P_WAIT, sys.argv[1], sys.argv[1:])
    server.shutdown()
    raise SystemExit(process)
