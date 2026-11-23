# Copyright 2026 VM/370 OTel Exporter contributors
# SPDX-License-Identifier: Apache-2.0

"""HTTP server for ``/metrics``. The listen address is loopback only."""

from __future__ import annotations

from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from vm370_otel_exporter.models import Snapshot
from vm370_otel_exporter.prometheus import CONTENT_TYPE, render_prometheus

SnapshotLoader = Callable[[], Snapshot]

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9370


class ListenError(ValueError):
    """The requested listen address is not loopback."""


def normalize_listen(host: str) -> str:
    """Accept the IPv4 loopback address and refuse every other host."""

    if host in {DEFAULT_HOST, "localhost"}:
        return DEFAULT_HOST
    raise ListenError(f"{host} is not a loopback address; /metrics binds to {DEFAULT_HOST}")


def make_server(
    snapshot: Snapshot | SnapshotLoader,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
):
    """Bind ``/metrics`` on loopback and return the server without serving."""

    bound_host = normalize_listen(host)
    load: SnapshotLoader = snapshot if callable(snapshot) else (lambda: snapshot)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if urlparse(self.path).path != "/metrics":
                self.send_error(404)
                return
            body = render_prometheus(load())
            self.send_response(200)
            self.send_header("Content-Type", CONTENT_TYPE)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer((bound_host, port), Handler)
    return server
