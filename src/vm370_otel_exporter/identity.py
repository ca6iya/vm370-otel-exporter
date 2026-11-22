# Copyright 2026 VM/370 OTel Exporter contributors
# SPDX-License-Identifier: Apache-2.0

"""Resource attributes taken from a VMMON DIAG X'00' line.

The line VMMON prints is ``HYPERVISOR=`` plus an 8-byte system name and
``VM_USERID=`` plus an 8-byte userid. Both ``zvm.hypervisor`` and
``zvm.system.name`` receive the system name. ``zvm.exporter.guest`` receives
the userid. ``host.arch`` is copied only from a ``host.arch=`` line.
"""

from __future__ import annotations

import re

_VMMON = re.compile(r"HYPERVISOR=(.{1,8}?)\s+VM_USERID=(.{1,8})")
_ARCH = re.compile(r"(?m)^[ \t]*host\.arch[ \t]*=[ \t]*([A-Za-z0-9_.:/-]+)[ \t]*$")


def identity_from_text(text: str) -> dict[str, str]:
    """Return VMMON identity attributes, plus host.arch only when a line sets it."""

    attributes: dict[str, str] = {}
    found = list(_VMMON.finditer(text))
    if found:
        match = found[-1]
        hypervisor = match.group(1).strip()
        guest = match.group(2).strip()
        if hypervisor and guest:
            attributes["zvm.hypervisor"] = hypervisor
            attributes["zvm.system.name"] = hypervisor
            attributes["zvm.exporter.guest"] = guest
    arch = list(_ARCH.finditer(text))
    if arch:
        attributes["host.arch"] = arch[-1].group(1)
    return attributes
