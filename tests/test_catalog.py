# Copyright 2026 VM/370 OTel Exporter contributors
# SPDX-License-Identifier: Apache-2.0

from vm370_otel_exporter.catalog import CATALOG, FORBIDDEN_NAMES, assert_catalog, prometheus_name

EXPECTED = {
    "zvm.vm370.cpu.utilization",
    "zvm.vm370.apu.utilization",
    "zvm.vm370.queue.depth",
    "zvm.vm370.storage.utilization",
    "zvm.vm370.paging.ratio",
    "zvm.vm370.paging.reads",
    "zvm.vm370.paging.writes",
    "zvm.vm370.paging.disk",
    "zvm.vm370.paging.drum",
    "zvm.vm370.guest.pages.resident",
    "zvm.vm370.guest.pages.working_set",
    "zvm.vm370.guest.vtime",
    "zvm.vm370.guest.ttime",
    "zvm.vm370.guest.sio",
    "zvm.vm370.guest.rdr",
    "zvm.vm370.guest.prt",
    "zvm.vm370.guest.pch",
    "zvm.vm370.guest.info",
    "zvm.vm370.storage.size",
    "zvm.vm370.storage.nucleus",
    "zvm.vm370.storage.dynamic_paging",
    "zvm.vm370.storage.trace_table",
    "zvm.vm370.storage.free",
    "zvm.vm370.storage.virtual_real",
}


def test_catalog_is_exactly_the_vm370_names() -> None:
    assert set(CATALOG) == EXPECTED
    assert_catalog()
    for name, defn in CATALOG.items():
        assert name.startswith("zvm.vm370.")
        assert defn.name == name
        assert "steal" not in name.lower()
        assert "steal" not in defn.description.lower()
        assert "rate" not in name.lower()
        assert not defn.unit.endswith("/s")
        assert name not in FORBIDDEN_NAMES
        assert not name.startswith("zvm.linux.")
        scraped = prometheus_name(defn)
        assert scraped.startswith("zvm_vm370_")
        assert "steal" not in scraped
        assert "rate" not in scraped


def test_storage_percent_is_not_named_steal() -> None:
    defn = CATALOG["zvm.vm370.storage.utilization"]
    assert defn.type == "gauge"
    assert defn.unit == "1"
    assert "steal" not in defn.name
    assert "steal" not in prometheus_name(defn)


def test_disk_and_drum_are_allocation_gauges() -> None:
    for name in ("zvm.vm370.paging.disk", "zvm.vm370.paging.drum"):
        defn = CATALOG[name]
        assert defn.type == "gauge"
        assert defn.unit == "{page}"
        assert not prometheus_name(defn).endswith("_total")
    assert CATALOG["zvm.vm370.paging.reads"].type == "counter"
    assert CATALOG["zvm.vm370.paging.writes"].type == "counter"


def test_reads_is_a_cumulative_counter() -> None:
    defn = CATALOG["zvm.vm370.paging.reads"]
    assert defn.type == "counter"
    assert defn.unit == "{page}"
    assert "rate" not in defn.name
    assert "rate" not in prometheus_name(defn)
    assert not prometheus_name(defn).endswith("_per_second")
    writes = CATALOG["zvm.vm370.paging.writes"]
    assert writes.type == "counter"
    assert writes.unit == "{page}"
