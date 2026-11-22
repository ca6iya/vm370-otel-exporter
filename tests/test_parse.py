# Copyright 2026 VM/370 OTel Exporter contributors
# SPDX-License-Identifier: Apache-2.0

from tests.conftest import one
from vm370_otel_exporter.parse import parse_text


def test_indicate_load(load_fixture) -> None:
    snapshot = parse_text(load_fixture("indicate_load.txt"))
    assert snapshot.resource == {}
    assert one(snapshot, "zvm.vm370.cpu.utilization").value == 0.02
    assert one(snapshot, "zvm.vm370.cpu.utilization").value != 2
    assert one(snapshot, "zvm.vm370.apu.utilization").value == 0
    assert one(snapshot, "zvm.vm370.storage.utilization").value == 0.12
    assert one(snapshot, "zvm.vm370.storage.utilization").value != 12
    assert one(snapshot, "zvm.vm370.paging.ratio").value == 1.0
    assert one(snapshot, "zvm.vm370.paging.ratio").value != 0.01
    assert one(snapshot, "zvm.vm370.queue.depth", **{"zvm.vm370.queue": "q1"}).value == 0
    assert one(snapshot, "zvm.vm370.queue.depth", **{"zvm.vm370.queue": "q2"}).value == 0
    assert {sample.name for sample in snapshot.samples} == {
        "zvm.vm370.cpu.utilization",
        "zvm.vm370.apu.utilization",
        "zvm.vm370.storage.utilization",
        "zvm.vm370.paging.ratio",
        "zvm.vm370.queue.depth",
    }
    assert all(sample.name.startswith("zvm.vm370.") for sample in snapshot.samples)
    assert all("steal" not in sample.name for sample in snapshot.samples)


def test_indicate_user_counts_are_cumulative(load_fixture) -> None:
    snapshot = parse_text(load_fixture("indicate_user.txt"))
    user = {"zvm.vm370.userid": "WAKEUP"}
    assert one(snapshot, "zvm.vm370.guest.pages.resident", **user).value == 162
    assert one(snapshot, "zvm.vm370.guest.pages.working_set", **user).value == 73
    reads = one(snapshot, "zvm.vm370.paging.reads", **user)
    assert reads.value == 34
    assert reads.value != 34 / 60
    assert one(snapshot, "zvm.vm370.paging.writes", **user).value == 0
    assert one(snapshot, "zvm.vm370.paging.disk", **user).value == 0
    assert one(snapshot, "zvm.vm370.paging.drum", **user).value == 0
    assert one(snapshot, "zvm.vm370.guest.vtime", **user).value == 0
    assert one(snapshot, "zvm.vm370.guest.ttime", **user).value == 0
    assert one(snapshot, "zvm.vm370.guest.sio", **user).value == 1271
    assert one(snapshot, "zvm.vm370.guest.rdr", **user).value == 0
    assert one(snapshot, "zvm.vm370.guest.prt", **user).value == 0
    assert one(snapshot, "zvm.vm370.guest.pch", **user).value == 0
    assert "zvm.vm370.paging.rate" not in {sample.name for sample in snapshot.samples}


def test_query_names(load_fixture) -> None:
    snapshot = parse_text(load_fixture("query_names.txt"))
    wakeup = one(snapshot, "zvm.vm370.guest.info", **{"zvm.vm370.userid": "WAKEUP"})
    batch = one(snapshot, "zvm.vm370.guest.info", **{"zvm.vm370.userid": "CMSBATCH"})
    assert wakeup.value == 1
    assert wakeup.attributes["zvm.vm370.terminal"] == "DSC"
    assert batch.value == 1
    assert batch.attributes["zvm.vm370.terminal"] == "DSC"
    assert len(snapshot.samples) == 2


def test_query_names_terminal_address() -> None:
    text = "WAKEUP   - DSC, CMSBATCH - DSC, CPWATCH  - DSC, OPERATOR - 009"
    snapshot = parse_text(text)
    assert one(
        snapshot, "zvm.vm370.guest.info", **{"zvm.vm370.userid": "OPERATOR"}
    ).attributes["zvm.vm370.terminal"] == "009"
    assert len(snapshot.samples) == 4


def test_ipl_kilobytes_become_bytes(load_fixture) -> None:
    snapshot = parse_text(load_fixture("ipl.txt"))
    expected = {
        "zvm.vm370.storage.size": 16384,
        "zvm.vm370.storage.nucleus": 336,
        "zvm.vm370.storage.dynamic_paging": 14788,
        "zvm.vm370.storage.trace_table": 240,
        "zvm.vm370.storage.free": 1020,
        "zvm.vm370.storage.virtual_real": 0,
    }
    assert {sample.name for sample in snapshot.samples} == set(expected)
    for name, kilobytes in expected.items():
        assert one(snapshot, name).value == kilobytes * 1024


def test_vmmon_identity_and_no_host_arch(load_fixture) -> None:
    snapshot = parse_text(load_fixture("vmmon.txt"))
    assert snapshot.samples == ()
    assert snapshot.resource == {
        "zvm.hypervisor": "VM/370",
        "zvm.system.name": "VM/370",
        "zvm.exporter.guest": "CMSUSER",
    }
    assert "host.arch" not in snapshot.resource
    blob = " ".join(snapshot.resource.values())
    assert "7.3.0" not in blob
    assert "3906" not in blob
    assert "z/VM" not in blob


def test_no_match_emits_nothing(load_fixture) -> None:
    snapshot = parse_text(load_fixture("no_match.txt"))
    assert snapshot.samples == ()
    assert snapshot.resource == {}
    assert "host.arch" not in snapshot.resource


def test_clock_form_and_userid_do_not_leak() -> None:
    text = "\n".join(
        [
            "ind user WAKEUP",
            "VTIME=001:30 TTIME=000:05 SIO=000010 RDR-000001 PRT-000002 PCH-000003",
            "ind user CMSBATCH",
            "PAGES: RES-0004 WS-0005 READS=000020 WRITES=000006 DISK-0007 DRUM-0008",
            "VTIME=1:02:03 TTIME=00:00:00 SIO=000009",
            "VTIME=12:3",
            "TTIME=000:0",
        ]
    )
    snapshot = parse_text(text)
    wakeup = {"zvm.vm370.userid": "WAKEUP"}
    batch = {"zvm.vm370.userid": "CMSBATCH"}
    assert one(snapshot, "zvm.vm370.guest.vtime", **wakeup).value == 90
    assert one(snapshot, "zvm.vm370.guest.ttime", **wakeup).value == 5
    assert one(snapshot, "zvm.vm370.paging.reads", **batch).value == 20
    assert one(snapshot, "zvm.vm370.guest.sio", **batch).value == 9
    names = {(sample.name, sample.attributes["zvm.vm370.userid"]) for sample in snapshot.samples}
    assert ("zvm.vm370.guest.vtime", "CMSBATCH") not in names
    assert ("zvm.vm370.guest.ttime", "CMSBATCH") not in names
    assert ("zvm.vm370.paging.reads", "WAKEUP") not in names


def test_percent_and_ratio_edges() -> None:
    snapshot = parse_text("CPU-100%  APU-000%  Q1-03  Q2-10  STORAGE-100%  RATIO-02.5")
    assert one(snapshot, "zvm.vm370.cpu.utilization").value == 1
    assert one(snapshot, "zvm.vm370.apu.utilization").value == 0
    assert one(snapshot, "zvm.vm370.storage.utilization").value == 1
    assert one(snapshot, "zvm.vm370.paging.ratio").value == 2.5
    assert one(snapshot, "zvm.vm370.queue.depth", **{"zvm.vm370.queue": "q1"}).value == 3
    assert one(snapshot, "zvm.vm370.queue.depth", **{"zvm.vm370.queue": "q2"}).value == 10


def test_host_arch_is_set_only_from_an_explicit_line() -> None:
    snapshot = parse_text("host.arch=s370\nCPU-002%")
    assert snapshot.resource == {"host.arch": "s370"}
    assert one(snapshot, "zvm.vm370.cpu.utilization").value == 0.02
    bare = parse_text("host.arch s390x")
    assert bare.resource == {}


def test_foreign_identity_text_is_ignored() -> None:
    text = "\n".join(
        [
            "VM00 Control Program: z/VM 7.3.0",
            "Type: 3906",
            "Architecture s390x",
            load_line(),
        ]
    )
    snapshot = parse_text(text)
    assert snapshot.resource == {}
    assert "host.arch" not in snapshot.resource
    assert one(snapshot, "zvm.vm370.cpu.utilization").value == 0.02


def load_line() -> str:
    return "CPU-002%  APU-000%  Q1-00  Q2-00  STORAGE-012%  RATIO-01.0"


def test_every_fixture_name_stays_in_the_vm370_prefix(load_fixture) -> None:
    text = "\n".join(
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
    snapshot = parse_text(text)
    assert snapshot.samples
    assert all(sample.name.startswith("zvm.vm370.") for sample in snapshot.samples)
    assert all("steal" not in sample.name for sample in snapshot.samples)
    assert all("rate" not in sample.name for sample in snapshot.samples)
    reads = one(snapshot, "zvm.vm370.paging.reads", **{"zvm.vm370.userid": "WAKEUP"})
    assert reads.value == 34
    assert snapshot.resource["zvm.hypervisor"] == "VM/370"
    assert snapshot.resource["zvm.system.name"] == "VM/370"
    assert snapshot.resource["zvm.exporter.guest"] == "CMSUSER"
    assert "host.arch" not in snapshot.resource
