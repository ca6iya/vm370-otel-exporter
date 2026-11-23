# Copyright 2026 VM/370 OTel Exporter contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path

import pytest

from vm370_otel_exporter.models import Sample, Snapshot

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def load_fixture():
    def _load(name: str) -> str:
        return (FIXTURES / name).read_text(encoding="utf-8")

    return _load


def one(snapshot: Snapshot, name: str, **attributes: str) -> Sample:
    matches = [
        sample
        for sample in snapshot.samples
        if sample.name == name
        and all(sample.attributes.get(key) == value for key, value in attributes.items())
    ]
    assert len(matches) == 1, (name, attributes, [(s.name, s.attributes, s.value) for s in snapshot.samples])
    return matches[0]
