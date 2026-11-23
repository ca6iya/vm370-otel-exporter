# Copyright 2026 VM/370 OTel Exporter contributors
# SPDX-License-Identifier: Apache-2.0

import pytest
import requests

from tests.conftest import FIXTURES
from vm370_otel_exporter.cli import main
from vm370_otel_exporter.otel import (
    OtlpSecurityError,
    _export_session,
    _NoDowngradeSession,
    prepare_otlp_export,
)


@pytest.fixture(autouse=True, scope="module")
def _clear_inherited_otlp_headers():
    with pytest.MonkeyPatch.context() as patch:
        patch.delenv("OTEL_EXPORTER_OTLP_HEADERS", raising=False)
        patch.delenv("OTEL_EXPORTER_OTLP_METRICS_HEADERS", raising=False)
        yield


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


def test_plaintext_session_ignores_netrc(tmp_path, monkeypatch) -> None:
    netrc = tmp_path / "netrc"
    netrc.write_text("machine 127.0.0.1 login user password secret\n", encoding="utf-8")
    netrc.chmod(0o600)
    monkeypatch.setenv("NETRC", str(netrc))
    session = _export_session(plaintext=True, endpoint="http://127.0.0.1:4318/v1/metrics")
    prepared = session.prepare_request(requests.Request("POST", "http://127.0.0.1:4318/v1/metrics"))
    assert session.trust_env is False
    assert "Authorization" not in prepared.headers
    secure = _export_session(plaintext=False, endpoint="https://collector.example/v1/metrics")
    secure_request = secure.prepare_request(
        requests.Request("POST", "https://collector.example/v1/metrics")
    )
    assert secure.trust_env is True
    assert "Authorization" not in secure_request.headers


def test_https_session_can_use_netrc(tmp_path, monkeypatch) -> None:
    netrc = tmp_path / "netrc"
    netrc.write_text("machine collector.example login user password secret\n", encoding="utf-8")
    netrc.chmod(0o600)
    monkeypatch.setenv("NETRC", str(netrc))
    session = _export_session(plaintext=False, endpoint="https://collector.example/v1/metrics")
    prepared = session.prepare_request(requests.Request("POST", "https://collector.example/v1/metrics"))
    assert prepared.headers["Authorization"].startswith("Basic ")


def test_cross_origin_https_redirect_drops_credentials() -> None:
    session = _NoDowngradeSession()
    original = requests.Request("POST", "https://collector.example/v1/metrics").prepare()
    prepared = requests.Request(
        "POST",
        "https://other.example/v1/metrics",
        headers={"x-api-key": "secret", "Content-Type": "application/x-protobuf"},
    ).prepare()
    response = requests.Response()
    response.url = "https://collector.example/v1/metrics"
    response.request = original
    session.rebuild_auth(prepared, response)
    assert "x-api-key" not in prepared.headers
    assert prepared.headers["Content-Type"] == "application/x-protobuf"


def test_later_hop_does_not_restore_netrc_off_the_configured_origin(tmp_path, monkeypatch) -> None:
    netrc = tmp_path / "netrc"
    netrc.write_text("machine collector.example login user password secret\n", encoding="utf-8")
    netrc.chmod(0o600)
    monkeypatch.setenv("NETRC", str(netrc))
    session = _export_session(plaintext=False, endpoint="https://collector.example/v1/metrics")
    original = requests.Request("POST", "https://collector.example:8443/a").prepare()
    prepared = requests.Request(
        "POST",
        "https://collector.example:8443/b",
        headers={"Content-Type": "application/x-protobuf"},
    ).prepare()
    response = requests.Response()
    response.url = "https://collector.example:8443/a"
    response.request = original
    session.rebuild_auth(prepared, response)
    assert "Authorization" not in prepared.headers
    assert prepared.headers["Content-Type"] == "application/x-protobuf"


def test_same_origin_https_redirect_keeps_credentials() -> None:
    session = _NoDowngradeSession()
    original = requests.Request("POST", "https://collector.example/v1/metrics").prepare()
    prepared = requests.Request(
        "POST",
        "https://collector.example/v1/metrics/extra",
        headers={"x-api-key": "secret", "Content-Type": "application/x-protobuf"},
    ).prepare()
    response = requests.Response()
    response.url = "https://collector.example/v1/metrics"
    response.request = original
    session.rebuild_auth(prepared, response)
    assert prepared.headers["x-api-key"] == "secret"
    assert prepared.headers["Content-Type"] == "application/x-protobuf"


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
