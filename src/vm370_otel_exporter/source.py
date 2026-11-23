# Copyright 2026 VM/370 OTel Exporter contributors
# SPDX-License-Identifier: Apache-2.0

"""Load a snapshot from memory or by re-reading a CP text file.

The caller supplies the file. A playground capture may overwrite it;
``/metrics`` and OTLP callbacks then parse the new text on the next scrape.
This process does not collect CP text itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from vm370_otel_exporter.models import Snapshot
from vm370_otel_exporter.parse import parse_text


@dataclass
class SnapshotSource:
    """Return the last snapshot, re-reading ``path`` when it is set."""

    snapshot: Snapshot
    path: Path | None = None

    def get(self) -> Snapshot:
        if self.path is not None:
            self.snapshot = parse_text(self.path.read_text(encoding="utf-8", errors="replace"))
        return self.snapshot
