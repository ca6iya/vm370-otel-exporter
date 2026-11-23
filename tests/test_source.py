# Copyright 2026 VM/370 OTel Exporter contributors
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

from tests.test_server import _get
from vm370_otel_exporter.parse import parse_text
from vm370_otel_exporter.server import make_server
from vm370_otel_exporter.source import SnapshotSource


def test_metrics_rereads_text_file(tmp_path: Path, load_fixture) -> None:
    path = tmp_path / "cp.txt"
    path.write_text(load_fixture("indicate_load.txt"), encoding="utf-8")
    source = SnapshotSource(parse_text(path.read_text(encoding="utf-8")), path=path)
    server = make_server(source.get, port=0)
    import threading

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        first = _get(f"http://{host}:{port}/metrics")
        path.write_text("CPU-050%  APU-000%  Q1-00  Q2-00  STORAGE-012%  RATIO-01.0\n", encoding="utf-8")
        second = _get(f"http://{host}:{port}/metrics")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    assert b"0.02" in first
    assert b"0.5" in second
    assert b"steal" not in second.lower()
