# Copyright 2026 VM/370 OTel Exporter contributors
# SPDX-License-Identifier: Apache-2.0

"""Parsed CP text as catalog samples and resource attributes."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Sample:
    name: str
    value: float
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Snapshot:
    samples: tuple[Sample, ...]
    resource: dict[str, str]

    @staticmethod
    def empty() -> Snapshot:
        return Snapshot((), {})
