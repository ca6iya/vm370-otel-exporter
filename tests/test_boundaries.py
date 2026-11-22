# Copyright 2026 VM/370 OTel Exporter contributors
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "vm370_otel_exporter"

FORBIDDEN = (
    "subprocess",
    "feilong",
    "vmcp",
    "hypfs",
    "monreader",
    "/proc",
    "hercules",
    "sysinfo",
    "3906",
    "7.3.0",
    "os.system",
    "popen",
    "urlopen",
    "shell=true",
)


def test_package_does_not_collect_or_dispatch() -> None:
    files = list(SRC.rglob("*.py"))
    assert files
    for path in files:
        text = path.read_text(encoding="utf-8").lower()
        for token in FORBIDDEN:
            assert token not in text, f"{path.name} contains {token}"
