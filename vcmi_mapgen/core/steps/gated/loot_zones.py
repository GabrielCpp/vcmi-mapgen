"""What gating changes in a level's zone records and walk targets."""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import replace

from vcmi_mapgen.core.model import PlacedObject, Tile
from vcmi_mapgen.core.planning.zone_index import ZoneRecord


def mark_loot_zones(records: Sequence[ZoneRecord], sealed: Collection[int]) -> list[ZoneRecord]:
    """The records with every sealed zone marked as a loot zone."""
    return [replace(zr, loot_zone=True) if zr.zid in sealed else zr for zr in records]


def walk_targets(
    targets: Sequence[Tile],
    new: Sequence[PlacedObject],
    records: Sequence[ZoneRecord],
    sealed: Collection[int],
) -> list[Tile]:
    """The walk targets after gating: the old targets and each new object with a purpose,
    less every tile inside a sealed zone."""
    interior = {t for zr in records if zr.zid in sealed for t in zr.ts}
    added = [(o.x, o.y) for o in new if o.purpose]
    return [t for t in (*targets, *added) if t not in interior]
