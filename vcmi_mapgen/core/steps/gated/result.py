"""GatedStep's result."""

from __future__ import annotations

from dataclasses import dataclass, field

from vcmi_mapgen.core.steps.gated.placer import LootAccess


@dataclass
class GatedResult:
    """The access of every loot zone, per level and zone id."""

    access: dict[int, dict[int, LootAccess]] = field(default_factory=dict)
