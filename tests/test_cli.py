# Copyright 2026 VM/370 OTel Exporter contributors
# SPDX-License-Identifier: Apache-2.0

import sys
from io import StringIO

from tests.conftest import FIXTURES
from vm370_otel_exporter.cli import main


def test_catalog_lists_dotted_names(capsys) -> None:
    assert main(["--catalog"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines
    assert all(line.startswith("zvm.vm370.") for line in lines)
    assert all("steal" not in line for line in lines)
    assert all("rate" not in line.split()[0] for line in lines)


def test_once_reads_a_file(capsys) -> None:
    assert main(["--text", str(FIXTURES / "indicate_load.txt"), "--once"]) == 0
    out = capsys.readouterr().out
    assert "zvm_vm370_cpu_utilization" in out
    assert "0.02" in out
    assert "steal" not in out.lower()


def test_once_reads_stdin(monkeypatch, capsys, load_fixture) -> None:
    monkeypatch.setattr(sys, "stdin", StringIO(load_fixture("query_names.txt")))
    assert main(["--text", "-", "--once"]) == 0
    out = capsys.readouterr().out
    assert 'zvm_vm370_userid="WAKEUP"' in out
    assert 'zvm_vm370_terminal="DSC"' in out


def test_refuses_non_loopback(capsys) -> None:
    code = main(
        ["--text", str(FIXTURES / "indicate_load.txt"), "--listen", "0.0.0.0", "--port", "9370"]
    )
    assert code == 2
    assert "127.0.0.1" in capsys.readouterr().err
