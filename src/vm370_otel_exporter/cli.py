# Copyright 2026 VM/370 OTel Exporter contributors
# SPDX-License-Identifier: Apache-2.0

"""Command line for file or stdin CP text."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from vm370_otel_exporter.catalog import CATALOG
from vm370_otel_exporter.otel import OtlpSecurityError, start_otlp
from vm370_otel_exporter.parse import parse_text
from vm370_otel_exporter.prometheus import render_prometheus
from vm370_otel_exporter.server import DEFAULT_HOST, DEFAULT_PORT, ListenError, make_server
from vm370_otel_exporter.source import SnapshotSource


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vm370-otel-exporter",
        description="Expose VM/370 CP text as Prometheus and optional OTLP metrics.",
    )
    parser.add_argument(
        "--text",
        help="CP text file. Use - to read stdin. With no --text, stdin is read when it is a pipe.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Write Prometheus text to stdout and exit.",
    )
    parser.add_argument(
        "--catalog",
        action="store_true",
        help="Print the dotted metric catalog and exit.",
    )
    parser.add_argument("--listen", default=DEFAULT_HOST, help="Loopback address (default 127.0.0.1).")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Listen port (default 9370).")
    parser.add_argument("--otlp", default="", help="Optional OTLP endpoint. Omit to skip OTLP.")
    parser.add_argument("--otlp-protocol", choices=("http", "grpc"), default="http")
    parser.add_argument(
        "--otlp-insecure",
        action="store_true",
        help="Use a plaintext OTLP channel. Refused when credential headers are set.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.catalog:
        for name in sorted(CATALOG):
            defn = CATALOG[name]
            print(f"{defn.name} {defn.type} {defn.unit}")
        return 0
    try:
        text = _read_text(args.text)
    except OSError as exc:
        print(f"cannot read CP text: {exc}", file=sys.stderr)
        return 2
    source = SnapshotSource(parse_text(text), path=_text_path(args.text))
    snapshot = source.get()
    runtime = None
    if args.otlp:
        try:
            runtime = start_otlp(
                args.otlp,
                args.otlp_protocol,
                snapshot,
                insecure=args.otlp_insecure,
                load_snapshot=source.get,
            )
        except OtlpSecurityError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    try:
        if args.once:
            sys.stdout.buffer.write(render_prometheus(snapshot))
            if runtime is not None:
                runtime.force_flush()
            return 0
        try:
            server = make_server(source.get, args.listen, args.port)
        except ListenError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        host, port = server.server_address[:2]
        print(f"listening on http://{host}:{port}/metrics", file=sys.stderr)
        server.serve_forever()
        return 0
    finally:
        if runtime is not None:
            runtime.shutdown()


def _read_text(path: str | None) -> str:
    if path is None or path == "-":
        if path is None and sys.stdin.isatty():
            raise OSError("pass --text FILE or pipe CP text on stdin")
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8", errors="replace")


def _text_path(path: str | None) -> Path | None:
    if path is None or path == "-":
        return None
    return Path(path)
