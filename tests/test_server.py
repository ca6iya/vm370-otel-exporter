# Copyright 2026 VM/370 OTel Exporter contributors
# SPDX-License-Identifier: Apache-2.0

import threading
import time
import urllib.error
import urllib.request

from vm370_otel_exporter.parse import parse_text
from vm370_otel_exporter.server import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    ListenError,
    make_server,
    normalize_listen,
)


def test_defaults_are_loopback() -> None:
    assert DEFAULT_HOST == "127.0.0.1"
    assert DEFAULT_PORT == 9370
    assert normalize_listen("localhost") == "127.0.0.1"
    try:
        normalize_listen("0.0.0.0")
    except ListenError as exc:
        assert "127.0.0.1" in str(exc)
    else:
        raise AssertionError("non-loopback listen was accepted")


def test_metrics_endpoint(load_fixture) -> None:
    snapshot = parse_text(load_fixture("indicate_load.txt"))
    server = make_server(snapshot, port=0)
    assert server.server_address[0] == "127.0.0.1"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        body = _get(f"http://{host}:{port}/metrics")
        missing = _status(f"http://{host}:{port}/api/cmd")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    assert b"zvm_vm370_cpu_utilization" in body
    assert b"steal" not in body.lower()
    assert missing == 404


def _get(url: str) -> bytes:
    deadline = time.monotonic() + 2
    last: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                return response.read()
        except (urllib.error.URLError, ConnectionError) as exc:
            last = exc
            time.sleep(0.05)
    raise AssertionError(last)


def _status(url: str) -> int:
    try:
        with urllib.request.urlopen(url, timeout=1) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code
