# Copyright 2026 VM/370 OTel Exporter contributors
# SPDX-License-Identifier: Apache-2.0

"""Dotted-name catalog for VM/370 R6 CP text.

Every instrument name starts with ``zvm.vm370.``. Prometheus exposition
names replace dots with underscores, append a unit suffix, and append
``_total`` on counters. Those scrape names are derived; the catalog names
are the contract.
"""

from __future__ import annotations

from dataclasses import dataclass

USER = ("zvm.vm370.userid",)
QUEUE = ("zvm.vm370.queue",)
GUEST_INFO = ("zvm.vm370.userid", "zvm.vm370.terminal")


@dataclass(frozen=True)
class MetricDef:
    name: str
    description: str
    type: str
    unit: str
    labels: tuple[str, ...] = ()


def _g(
    name: str,
    description: str,
    unit: str,
    labels: tuple[str, ...] = (),
) -> MetricDef:
    return MetricDef(name, description, "gauge", unit, labels)


def _c(
    name: str,
    description: str,
    unit: str,
    labels: tuple[str, ...] = (),
) -> MetricDef:
    return MetricDef(name, description, "counter", unit, labels)


CATALOG: dict[str, MetricDef] = {
    item.name: item
    for item in (
        _g(
            "zvm.vm370.cpu.utilization",
            "VM/370 INDICATE LOAD CPU-nnn% as a ratio from 0 to 1. 2% is 0.02.",
            "1",
        ),
        _g(
            "zvm.vm370.apu.utilization",
            "VM/370 INDICATE LOAD APU-nnn% as a ratio from 0 to 1.",
            "1",
        ),
        _g(
            "zvm.vm370.queue.depth",
            "VM/370 INDICATE LOAD Q1 or Q2 depth. zvm.vm370.queue is q1 or q2.",
            "{user}",
            QUEUE,
        ),
        _g(
            "zvm.vm370.storage.utilization",
            "VM/370 INDICATE LOAD STORAGE-nnn% as a ratio from 0 to 1. Real storage in use.",
            "1",
        ),
        _g(
            "zvm.vm370.paging.ratio",
            "VM/370 INDICATE LOAD RATIO as the printed factor.",
            "1",
        ),
        _c(
            "zvm.vm370.paging.reads",
            "Cumulative pages from VM/370 INDICATE USER READS= for one userid.",
            "{page}",
            USER,
        ),
        _c(
            "zvm.vm370.paging.writes",
            "Cumulative pages from VM/370 INDICATE USER WRITES= for one userid.",
            "{page}",
            USER,
        ),
        _g(
            "zvm.vm370.paging.disk",
            "Pages on disk for one userid when INDICATE USER runs. A later sample can be lower.",
            "{page}",
            USER,
        ),
        _g(
            "zvm.vm370.paging.drum",
            "Pages on drum for one userid when INDICATE USER runs. A later sample can be lower.",
            "{page}",
            USER,
        ),
        _g(
            "zvm.vm370.guest.pages.resident",
            "Resident pages from VM/370 INDICATE USER RES- for one userid.",
            "{page}",
            USER,
        ),
        _g(
            "zvm.vm370.guest.pages.working_set",
            "Working-set pages from VM/370 INDICATE USER WS- for one userid.",
            "{page}",
            USER,
        ),
        _c(
            "zvm.vm370.guest.vtime",
            "Virtual time from VM/370 INDICATE USER VTIME=mmm:ss, in seconds, for one userid.",
            "s",
            USER,
        ),
        _c(
            "zvm.vm370.guest.ttime",
            "Total time from VM/370 INDICATE USER TTIME=mmm:ss, in seconds, for one userid.",
            "s",
            USER,
        ),
        _c(
            "zvm.vm370.guest.sio",
            "Cumulative SIO count from VM/370 INDICATE USER SIO= for one userid.",
            "{operation}",
            USER,
        ),
        _c(
            "zvm.vm370.guest.rdr",
            "Cumulative reader count from VM/370 INDICATE USER RDR- for one userid.",
            "{operation}",
            USER,
        ),
        _c(
            "zvm.vm370.guest.prt",
            "Cumulative printer count from VM/370 INDICATE USER PRT- for one userid.",
            "{operation}",
            USER,
        ),
        _c(
            "zvm.vm370.guest.pch",
            "Cumulative punch count from VM/370 INDICATE USER PCH- for one userid.",
            "{operation}",
            USER,
        ),
        _g(
            "zvm.vm370.guest.info",
            "Logged-on guest from VM/370 QUERY NAMES. Value is 1.",
            "1",
            GUEST_INFO,
        ),
        _g(
            "zvm.vm370.storage.size",
            "IPL storage size, converted from K to bytes.",
            "By",
        ),
        _g(
            "zvm.vm370.storage.nucleus",
            "IPL nucleus size, converted from K to bytes.",
            "By",
        ),
        _g(
            "zvm.vm370.storage.dynamic_paging",
            "IPL dynamic paging size, converted from K to bytes.",
            "By",
        ),
        _g(
            "zvm.vm370.storage.trace_table",
            "IPL trace table size, converted from K to bytes.",
            "By",
        ),
        _g(
            "zvm.vm370.storage.free",
            "IPL free storage, converted from K to bytes.",
            "By",
        ),
        _g(
            "zvm.vm370.storage.virtual_real",
            "IPL virtual=real size, converted from K to bytes.",
            "By",
        ),
    )
}

FORBIDDEN_NAMES = frozenset(
    {
        "zvm.guest.cpu.time",
        "zvm.paging.allocated",
        "zvm.paging.rate",
        "zvm.system.cpu.utilization",
    }
)

_UNIT_SUFFIX = {
    "1": "",
    "By": "bytes",
    "s": "seconds",
    "{page}": "pages",
    "{user}": "users",
    "{operation}": "operations",
}


def prometheus_label(name: str) -> str:
    """Translate an attribute key to a Prometheus label name."""

    return name.replace(".", "_")


def prometheus_name(defn: MetricDef) -> str:
    """Derive the Prometheus exposition name for a catalog metric."""

    base = defn.name.replace(".", "_")
    suffix = _UNIT_SUFFIX[defn.unit]
    if suffix and not base.endswith("_" + suffix):
        base = f"{base}_{suffix}"
    if defn.type == "counter" and not base.endswith("_total"):
        base = f"{base}_total"
    return base


def assert_catalog() -> None:
    """Refuse a catalog that leaves the VM/370 name contract."""

    for name, defn in CATALOG.items():
        if not name.startswith("zvm.vm370."):
            raise RuntimeError(f"metric name {name} is outside zvm.vm370.")
        if name in FORBIDDEN_NAMES or name.startswith("zvm.linux."):
            raise RuntimeError(f"metric name {name} belongs to another exporter")
        if "steal" in name.lower() or "steal" in defn.description.lower():
            raise RuntimeError(f"metric {name} must not be named steal")
        if "rate" in name.lower() or defn.unit.endswith("/s"):
            raise RuntimeError(f"metric {name} must not be a rate")
        if defn.unit not in _UNIT_SUFFIX:
            raise RuntimeError(f"metric {name} has no Prometheus unit suffix")
        scraped = prometheus_name(defn)
        if not scraped.startswith("zvm_vm370_"):
            raise RuntimeError(f"prometheus name {scraped} drifted from zvm.vm370.")
        if "steal" in scraped or "rate" in scraped:
            raise RuntimeError(f"prometheus name {scraped} leaves the VM/370 contract")


assert_catalog()
