# Copyright 2026 VM/370 OTel Exporter contributors
# SPDX-License-Identifier: Apache-2.0

import requests

from tests.conftest import FIXTURES
from vm370_otel_exporter.cli import main
from vm370_otel_exporter.otel import OtlpSecurityError, _NoDowngradeSession, prepare_otlp_export


def test_schemeless_endpoint_uses_tls() -> None:
    grpc_url, grpc_plain = prepare_otlp_export("collector.example:4317", "grpc", insecure=False)
    http_url, http_plain = prepare_otlp_export("collector.example:4318", "http", insecure=False)
    assert grpc_url == "https://collector.example:4317"
    assert grpc_plain is False
    assert http_url == "https://collector.example:4318/v1/metrics"
    assert http_plain is False


def test_explicit_http_stays_plaintext_without_credentials() -> None:
    url, plaintext = prepare_otlp_export("http://127.0.0.1:4318", "http", insecure=False)
    assert url == "http://127.0.0.1:4318/v1/metrics"
    assert plaintext is True


def test_insecure_flag_is_plaintext_without_credentials() -> None:
    url, plaintext = prepare_otlp_export("collector.example:4317", "grpc", insecure=True)
    assert url == "http://collector.example:4317"
    assert plaintext is True


def test_credential_headers_refuse_plaintext(monkeypatch) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", "x-api-key=secret")
    try:
        prepare_otlp_export("http://127.0.0.1:4318", "http", insecure=False)
    except OtlpSecurityError as exc:
        assert "plaintext" in str(exc)
    else:
        raise AssertionError("plaintext export with credential headers was accepted")
    url, plaintext = prepare_otlp_export("collector.example:4317", "grpc", insecure=False)
    assert url.startswith("https://")
    assert plaintext is False


def test_cli_refuses_plaintext_credentials(monkeypatch, capsys) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_METRICS_HEADERS", "x-api-key=secret")
    code = main(
        [
            "--text",
            str(FIXTURES / "indicate_load.txt"),
            "--once",
            "--otlp",
            "http://127.0.0.1:4318",
        ]
    )
    assert code == 2
    assert "plaintext" in capsys.readouterr().err


def test_https_redirect_to_http_is_refused() -> None:
    session = _NoDowngradeSession()
    prepared = requests.Request(
        "POST",
        "http://collector.example/v1/metrics",
        headers={"x-api-key": "secret"},
    ).prepare()
    response = requests.Response()
    response.url = "https://collector.example/v1/metrics"
    try:
        session.rebuild_auth(prepared, response)
    except OtlpSecurityError as exc:
        assert "https to http" in str(exc)
    else:
        raise AssertionError("https to http redirect was accepted")
    assert prepared.headers["x-api-key"] == "secret"


def test_http_redirect_drops_credential_headers() -> None:
    session = _NoDowngradeSession()
    original = requests.Request("POST", "http://first.example/v1/metrics").prepare()
    prepared = requests.Request(
        "POST",
        "http://second.example/v1/metrics",
        headers={"x-api-key": "secret", "Content-Type": "application/x-protobuf"},
    ).prepare()
    response = requests.Response()
    response.url = "http://first.example/v1/metrics"
    response.request = original
    session.rebuild_auth(prepared, response)
    assert "x-api-key" not in prepared.headers
    assert prepared.headers["Content-Type"] == "application/x-protobuf"
