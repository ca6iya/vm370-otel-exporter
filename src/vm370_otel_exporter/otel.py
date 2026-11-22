# Copyright 2026 VM/370 OTel Exporter contributors
# SPDX-License-Identifier: Apache-2.0

"""Optional OTLP export. The meter scope name is ``vm370-otel-exporter``."""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

import requests
from opentelemetry.metrics import CallbackOptions, Observation
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader, MetricReader
from opentelemetry.sdk.resources import Resource

from vm370_otel_exporter import __version__
from vm370_otel_exporter.catalog import CATALOG
from vm370_otel_exporter.models import Snapshot

SCOPE_NAME = "vm370-otel-exporter"
_IDENTITY_KEYS = ("zvm.hypervisor", "zvm.system.name", "zvm.exporter.guest", "host.arch")
_CREDENTIAL_ENVS = (
    "OTEL_EXPORTER_OTLP_HEADERS",
    "OTEL_EXPORTER_OTLP_METRICS_HEADERS",
)
_SAFE_HTTP_HEADERS = frozenset(
    {"accept", "content-encoding", "content-length", "content-type", "user-agent"}
)


class OtlpSecurityError(ValueError):
    """The OTLP target would send credentials in cleartext."""


class _NoDowngradeSession(requests.Session):
    """Refuse an https export that redirects onto http."""

    def rebuild_auth(self, prepared_request, response):  # noqa: ANN001
        new_url = (prepared_request.url or "").lower()
        old_url = (getattr(response, "url", "") or "").lower()
        if new_url.startswith("http://") and old_url.startswith("https://"):
            raise OtlpSecurityError("refusing to follow an OTLP redirect from https to http")
        super().rebuild_auth(prepared_request, response)
        if new_url.startswith("http://"):
            for name in list(prepared_request.headers):
                if name.lower() not in _SAFE_HTTP_HEADERS:
                    del prepared_request.headers[name]


@dataclass
class OtelRuntime:
    provider: MeterProvider

    def force_flush(self, timeout_millis: int = 10000) -> bool:
        return bool(self.provider.force_flush(timeout_millis=timeout_millis))

    def shutdown(self) -> None:
        self.provider.shutdown()


def resource_attributes(snapshot: Snapshot) -> dict[str, str]:
    """Service identity plus VMMON fields that were actually present."""

    attributes = {
        "service.name": SCOPE_NAME,
        "service.version": __version__,
    }
    for key in _IDENTITY_KEYS:
        value = snapshot.resource.get(key, "")
        if value:
            attributes[key] = value
    return attributes


def build_provider(snapshot: Snapshot, reader: MetricReader | None = None) -> MeterProvider:
    """Register the catalog on a meter named ``vm370-otel-exporter``."""

    provider = MeterProvider(
        metric_readers=[reader] if reader is not None else [],
        resource=Resource(resource_attributes(snapshot)),
    )
    meter = provider.get_meter(SCOPE_NAME, __version__)
    for defn in CATALOG.values():
        callback = _callback(snapshot, defn.name, defn.type)
        if defn.type == "counter":
            meter.create_observable_counter(
                defn.name,
                callbacks=[callback],
                description=defn.description,
                unit=defn.unit,
            )
        else:
            meter.create_observable_gauge(
                defn.name,
                callbacks=[callback],
                description=defn.description,
                unit=defn.unit,
            )
    return provider


def collect_in_memory(snapshot: Snapshot) -> tuple[MeterProvider, InMemoryMetricReader]:
    """Collect one snapshot without opening a network connection."""

    reader = InMemoryMetricReader()
    provider = build_provider(snapshot, reader)
    return provider, reader


def _credential_headers_configured() -> bool:
    return any(os.environ.get(name, "").strip() for name in _CREDENTIAL_ENVS)


def prepare_otlp_export(endpoint: str, protocol: str, *, insecure: bool) -> tuple[str, bool]:
    """Return the export URL and whether that channel is plaintext.

    A schemeless address uses TLS. ``insecure`` or an explicit ``http://``
    URL selects plaintext, and plaintext is refused when credential headers
    or URL userinfo are present.
    """

    raw = endpoint.strip()
    if "://" not in raw:
        raw = ("http://" if insecure else "https://") + raw
    parts = urlsplit(raw)
    scheme = parts.scheme.lower()
    if scheme not in {"http", "https"}:
        raise OtlpSecurityError(f"unsupported OTLP scheme {scheme}")
    if insecure and scheme == "https":
        scheme = "http"
    plaintext = insecure or scheme == "http"
    if plaintext and (parts.username or parts.password or _credential_headers_configured()):
        raise OtlpSecurityError("refusing to send OTLP credentials over plaintext")
    path = parts.path
    if protocol != "grpc":
        path = path.rstrip("/")
        if not path.endswith("/v1/metrics"):
            path = f"{path}/v1/metrics" if path else "/v1/metrics"
    return urlunsplit((scheme, parts.netloc, path, parts.query, "")), plaintext


def metrics_endpoint(endpoint: str, protocol: str, *, insecure: bool = False) -> str:
    """Normalize an OTLP endpoint. HTTP exporters need ``/v1/metrics``."""

    url, _plaintext = prepare_otlp_export(endpoint, protocol, insecure=insecure)
    return url


def start_otlp(
    endpoint: str,
    protocol: str,
    snapshot: Snapshot,
    *,
    insecure: bool = False,
    timeout: float = 10.0,
    export_interval_ms: int = 15000,
) -> OtelRuntime:
    """Push the snapshot on an OTLP metric reader."""

    target, plaintext = prepare_otlp_export(endpoint, protocol, insecure=insecure)
    if protocol == "grpc":
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
            OTLPMetricExporter as GrpcExporter,
        )

        exporter = GrpcExporter(
            endpoint=target,
            insecure=plaintext,
            timeout=timeout,
        )
    else:
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
            OTLPMetricExporter as HttpExporter,
        )

        exporter = HttpExporter(
            endpoint=target,
            timeout=timeout,
            session=_NoDowngradeSession(),
        )
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

    reader = PeriodicExportingMetricReader(exporter, export_interval_millis=export_interval_ms)
    return OtelRuntime(build_provider(snapshot, reader))


def _callback(snapshot: Snapshot, name: str, instrument_type: str):
    def observe(_options: CallbackOptions) -> Iterable[Observation]:
        for sample in snapshot.samples:
            if sample.name != name:
                continue
            if instrument_type == "counter" and sample.value < 0:
                continue
            yield Observation(sample.value, dict(sample.attributes))

    return observe
