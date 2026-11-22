# Copyright 2026 VM/370 OTel Exporter contributors
# SPDX-License-Identifier: Apache-2.0

import re

import pytest

from vm370_otel_exporter.catalog import CATALOG, FORBIDDEN_NAMES, prometheus_name
from vm370_otel_exporter.otel import SCOPE_NAME, collect_in_memory
from vm370_otel_exporter.parse import parse_text
from vm370_otel_exporter.prometheus import render_prometheus

_SAMPLE = re.compile(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{([^}]*)\})?\s+(\S+)\s*$")


def _exposition(body: str) -> list[tuple[str, dict[str, str], float]]:
    found = []
    for line in body.splitlines():
        if not line or line.startswith("#"):
            continue
        match = _SAMPLE.match(line)
        assert match is not None, line
        labels: dict[str, str] = {}
        if match.group(3):
            for part in match.group(3).split(","):
                key, value = part.split("=", 1)
                labels[key] = value.strip('"')
        found.append((match.group(1), labels, float(match.group(4))))
    return found


def _combined(load_fixture) -> str:
    return "\n".join(
        load_fixture(name)
        for name in (
            "indicate_load.txt",
            "indicate_user.txt",
            "query_names.txt",
            "ipl.txt",
            "vmmon.txt",
            "no_match.txt",
        )
    )


def test_prometheus_text_uses_vm370_names(load_fixture) -> None:
    snapshot = parse_text(_combined(load_fixture))
    body = render_prometheus(snapshot).decode()
    assert "steal" not in body.lower()
    assert "7.3.0" not in body
    assert "3906" not in body
    assert "zvm_linux_" not in body
    for forbidden in FORBIDDEN_NAMES:
        assert forbidden.replace(".", "_") not in body
    samples = _exposition(body)
    assert samples
    assert all(name.startswith("zvm_vm370_") for name, _labels, _value in samples)
    cpu = [value for name, _labels, value in samples if name == "zvm_vm370_cpu_utilization"]
    assert cpu == pytest.approx([0.02])
    reads_name = prometheus_name(CATALOG["zvm.vm370.paging.reads"])
    assert reads_name == "zvm_vm370_paging_reads_pages_total"
    assert f"# TYPE {reads_name} counter" in body
    assert "per_second" not in reads_name
    reads = [
        value
        for name, labels, value in samples
        if name == reads_name and labels["zvm_vm370_userid"] == "WAKEUP"
    ]
    assert reads == pytest.approx([34.0])
    queues = {
        labels["zvm_vm370_queue"]: value
        for name, labels, value in samples
        if name == prometheus_name(CATALOG["zvm.vm370.queue.depth"])
    }
    assert queues == {"q1": 0.0, "q2": 0.0}
    size = [value for name, _labels, value in samples if name == "zvm_vm370_storage_size_bytes"]
    assert size == pytest.approx([16384 * 1024])


def test_otlp_scope_and_vmmon_identity(load_fixture) -> None:
    snapshot = parse_text(_combined(load_fixture))
    provider, reader = collect_in_memory(snapshot)
    try:
        data = reader.get_metrics_data()
    finally:
        provider.shutdown()
    assert data is not None
    resource_metrics = data.resource_metrics
    assert len(resource_metrics) == 1
    attributes = dict(resource_metrics[0].resource.attributes)
    assert attributes["service.name"] == SCOPE_NAME
    assert attributes["zvm.hypervisor"] == "VM/370"
    assert attributes["zvm.system.name"] == "VM/370"
    assert attributes["zvm.exporter.guest"] == "CMSUSER"
    assert "host.arch" not in attributes
    assert all("7.3.0" not in str(value) and "3906" not in str(value) for value in attributes.values())
    scopes = resource_metrics[0].scope_metrics
    assert len(scopes) == 1
    assert scopes[0].scope.name == SCOPE_NAME
    names = [metric.name for metric in scopes[0].metrics]
    assert names
    assert all(name.startswith("zvm.vm370.") for name in names)
    assert FORBIDDEN_NAMES.isdisjoint(names)
    assert all(not name.startswith("zvm.linux.") for name in names)
    reads = next(metric for metric in scopes[0].metrics if metric.name == "zvm.vm370.paging.reads")
    assert reads.data.data_points
    wakeup = [
        point.value
        for point in reads.data.data_points
        if point.attributes["zvm.vm370.userid"] == "WAKEUP"
    ]
    assert wakeup == pytest.approx([34])
