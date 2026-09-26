"""ZoneIndex: per-level zone records and walk targets shared by the placement steps after
vegetation."""

from __future__ import annotations

from dataclasses import dataclass, field

from vcmi_mapgen.models import Tile, ZoneRecord
from vcmi_mapgen.pipeline import LevelWorkspace, PlacementWorkspace
from vcmi_mapgen.steps.placement import scatter_reach


@dataclass
class ZoneIndex:
    """Per-level walk targets and zone records. GatedStep builds it once, and every later
    step mutates that same instance in place."""

    targets: dict[int, list[Tile]] = field(default_factory=dict)
    zone_records: dict[int, list[ZoneRecord]] = field(default_factory=dict)


def _level_records(lvl_ws: LevelWorkspace, targets: list[Tile]) -> list[ZoneRecord]:
    zone_records: list[ZoneRecord] = []
    for zid, zw in sorted(lvl_ws.zones.items()):
        reach = scatter_reach(zw.open_set - (zw.rim8 - zw.ent_bands), zw.prot)
        targets.extend(zw.approaches)
        targets.extend(r for r, _b, _o in zw.entrances)
        targets.extend(t for t in (lvl_ws.seaport_appr & zw.ts_full))
        zone_records.append(
            ZoneRecord(
                zid=zid,
                terrain=zw.terrain,
                ts=zw.ts_full,
                open_set=set(zw.open_set),
                passable=set(zw.passable),
                reach=reach,
                used=set(),
            )
        )
    return zone_records


def build_zone_index(workspace: PlacementWorkspace) -> ZoneIndex:
    """One zone record per zone and the walk targets of every level, and each level's
    ``hard_avoid`` set for BorderStep."""
    index = ZoneIndex()
    for level, lvl_ws in workspace.levels.items():
        targets: list[Tile] = []
        index.zone_records[level] = _level_records(lvl_ws, targets)
        index.targets[level] = targets
        hard_avoid: set[Tile] = set()
        for zw in lvl_ws.zones.values():
            hard_avoid |= set(zw.occupied) | set(zw.approaches)
        lvl_ws.hard_avoid = hard_avoid
    return index
