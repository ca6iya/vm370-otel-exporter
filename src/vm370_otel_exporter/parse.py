# Copyright 2026 VM/370 OTel Exporter contributors
# SPDX-License-Identifier: Apache-2.0

"""Parse VM/370 R6 CP text into catalog samples.

The caller supplies the text. A line that does not match a VM/370 pattern
contributes nothing.
"""

from __future__ import annotations

import re

from vm370_otel_exporter.catalog import CATALOG
from vm370_otel_exporter.identity import identity_from_text
from vm370_otel_exporter.models import Sample, Snapshot

_TIMESTAMP = re.compile(r"^(?:\d{2}:\d{2}:\d{2}\s+)+")
_IND_USER = re.compile(r"\bind user\s+([A-Za-z0-9$#@]+)", re.IGNORECASE)
_CPU = re.compile(r"\bCPU-(\d+)%")
_APU = re.compile(r"\bAPU-(\d+)%")
_QUEUE = re.compile(r"\bQ([12])-(\d+)\b")
_STORAGE_PCT = re.compile(r"\bSTORAGE-(\d+)%")
_RATIO = re.compile(r"\bRATIO-([0-9]+(?:\.[0-9]+)?)\b")
_RES = re.compile(r"\bRES-(\d+)\b")
_WS = re.compile(r"\bWS-(\d+)\b")
_READS = re.compile(r"\bREADS=(\d+)\b")
_WRITES = re.compile(r"\bWRITES=(\d+)\b")
_DISK = re.compile(r"\bDISK-(\d+)\b")
_DRUM = re.compile(r"\bDRUM-(\d+)\b")
_CLOCK = r"(\d+):(\d{2})(?=$|[\s,])"
_VTIME = re.compile(rf"\bVTIME={_CLOCK}")
_TTIME = re.compile(rf"\bTTIME={_CLOCK}")
_SIO = re.compile(r"\bSIO=(\d+)\b")
_RDR = re.compile(r"\bRDR-(\d+)\b")
_PRT = re.compile(r"\bPRT-(\d+)\b")
_PCH = re.compile(r"\bPCH-(\d+)\b")
_USERID = re.compile(r"^[A-Z0-9$#@]+$")
_IPL = re.compile(
    r"Storage size\s*=\s*(\d+)\s*K\s*,\s*"
    r"Nucleus\s*=\s*(\d+)\s*K\s*,\s*"
    r"Dynamic Paging\s*=\s*(\d+)\s*K\s*,\s*"
    r"Trace Table\s*=\s*(\d+)\s*K\s*,\s*"
    r"Free Storage\s*=\s*(\d+)\s*K\s*,\s*"
    r"Virtual=Real\s*=\s*(\d+)\s*K"
)

_IPL_NAMES = (
    "zvm.vm370.storage.size",
    "zvm.vm370.storage.nucleus",
    "zvm.vm370.storage.dynamic_paging",
    "zvm.vm370.storage.trace_table",
    "zvm.vm370.storage.free",
    "zvm.vm370.storage.virtual_real",
)

_PAGE_FIELDS = (
    (_RES, "zvm.vm370.guest.pages.resident"),
    (_WS, "zvm.vm370.guest.pages.working_set"),
    (_READS, "zvm.vm370.paging.reads"),
    (_WRITES, "zvm.vm370.paging.writes"),
    (_DISK, "zvm.vm370.paging.disk"),
    (_DRUM, "zvm.vm370.paging.drum"),
)


def parse_text(text: str) -> Snapshot:
    """Parse CP text. Unmatched input yields an empty sample list."""

    found: dict[tuple[str, tuple[tuple[str, str], ...]], Sample] = {}
    _parse_load(text, found)
    _parse_ipl(text, found)
    _parse_lines(text, found)
    samples = tuple(found[key] for key in sorted(found))
    snapshot = Snapshot(samples, identity_from_text(text))
    _validate(snapshot)
    return snapshot


def _validate(snapshot: Snapshot) -> None:
    allowed = {"zvm.hypervisor", "zvm.system.name", "zvm.exporter.guest", "host.arch"}
    extra = set(snapshot.resource) - allowed
    if extra:
        raise RuntimeError(f"unexpected resource attributes: {sorted(extra)}")
    for sample in snapshot.samples:
        if sample.name not in CATALOG or not sample.name.startswith("zvm.vm370."):
            raise RuntimeError(f"sample {sample.name} is outside the VM/370 catalog")
        labels = CATALOG[sample.name].labels
        if tuple(sample.attributes) != labels:
            raise RuntimeError(f"sample {sample.name} labels do not match the catalog")


def _put(found: dict[tuple[str, tuple[tuple[str, str], ...]], Sample], sample: Sample) -> None:
    key = (sample.name, tuple(sample.attributes.items()))
    found[key] = sample


def _sample(name: str, value: float, **attrs: str) -> Sample:
    labels = CATALOG[name].labels
    attributes = {label: attrs.get(label, "") for label in labels}
    return Sample(name, float(value), attributes)


def _last(pattern: re.Pattern[str], text: str) -> re.Match[str] | None:
    found = list(pattern.finditer(text))
    if not found:
        return None
    return found[-1]


def _percent(raw: str) -> float:
    return int(raw) / 100.0


def _parse_load(text: str, found: dict[tuple[str, tuple[tuple[str, str], ...]], Sample]) -> None:
    cpu = _last(_CPU, text)
    if cpu:
        _put(found, _sample("zvm.vm370.cpu.utilization", _percent(cpu.group(1))))
    apu = _last(_APU, text)
    if apu:
        _put(found, _sample("zvm.vm370.apu.utilization", _percent(apu.group(1))))
    storage = _last(_STORAGE_PCT, text)
    if storage:
        _put(found, _sample("zvm.vm370.storage.utilization", _percent(storage.group(1))))
    ratio = _last(_RATIO, text)
    if ratio:
        _put(found, _sample("zvm.vm370.paging.ratio", float(ratio.group(1))))
    queues: dict[str, int] = {}
    for match in _QUEUE.finditer(text):
        queues[f"q{match.group(1)}"] = int(match.group(2))
    for queue, depth in queues.items():
        _put(found, _sample("zvm.vm370.queue.depth", depth, **{"zvm.vm370.queue": queue}))


def _parse_ipl(text: str, found: dict[tuple[str, tuple[tuple[str, str], ...]], Sample]) -> None:
    match = _last(_IPL, text)
    if not match:
        return
    for name, raw in zip(_IPL_NAMES, match.groups(), strict=True):
        _put(found, _sample(name, int(raw) * 1024))


def _parse_lines(text: str, found: dict[tuple[str, tuple[tuple[str, str], ...]], Sample]) -> None:
    userid = ""
    for raw_line in text.splitlines():
        line = _TIMESTAMP.sub("", raw_line.strip())
        if not line:
            continue
        user_match = _IND_USER.search(line)
        if user_match:
            userid = user_match.group(1).upper()
        elif line.startswith("/("):
            continue
        if "PAGES:" in line:
            _parse_pages(line, userid, found)
        if any(token in line for token in ("VTIME=", "TTIME=", "SIO=", "RDR-", "PRT-", "PCH-")):
            _parse_times(line, userid, found)
        if user_match is None and " - " in line:
            _parse_names(line, found)


def _parse_pages(
    line: str,
    userid: str,
    found: dict[tuple[str, tuple[tuple[str, str], ...]], Sample],
) -> None:
    for pattern, name in _PAGE_FIELDS:
        match = pattern.search(line)
        if match:
            _put(found, _sample(name, int(match.group(1)), **{"zvm.vm370.userid": userid}))


def _parse_times(
    line: str,
    userid: str,
    found: dict[tuple[str, tuple[tuple[str, str], ...]], Sample],
) -> None:
    attrs = {"zvm.vm370.userid": userid}
    vtime = _VTIME.search(line)
    if vtime:
        _put(found, _sample("zvm.vm370.guest.vtime", _seconds(vtime), **attrs))
    ttime = _TTIME.search(line)
    if ttime:
        _put(found, _sample("zvm.vm370.guest.ttime", _seconds(ttime), **attrs))
    for pattern, name in (
        (_SIO, "zvm.vm370.guest.sio"),
        (_RDR, "zvm.vm370.guest.rdr"),
        (_PRT, "zvm.vm370.guest.prt"),
        (_PCH, "zvm.vm370.guest.pch"),
    ):
        match = pattern.search(line)
        if match:
            _put(found, _sample(name, int(match.group(1)), **attrs))


def _seconds(match: re.Match[str]) -> int:
    return int(match.group(1)) * 60 + int(match.group(2))


def _parse_names(line: str, found: dict[tuple[str, tuple[tuple[str, str], ...]], Sample]) -> None:
    if line.startswith("/"):
        return
    for part in line.split(","):
        if " - " not in part:
            continue
        userid, terminal = (piece.strip() for piece in part.split(" - ", 1))
        if _USERID.fullmatch(userid) and terminal:
            _put(
                found,
                _sample(
                    "zvm.vm370.guest.info",
                    1,
                    **{"zvm.vm370.userid": userid, "zvm.vm370.terminal": terminal},
                ),
            )
