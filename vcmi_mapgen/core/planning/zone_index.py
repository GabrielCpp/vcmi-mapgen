"""ZoneIndex: per-level zone records and walk targets shared by the placement steps after
vegetation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.placement.place import scatter_reach
from vcmi_mapgen.core.placement.site import PlacedZone
from vcmi_mapgen.core.planning.zone_plan import Landings, PlanLevel, ZonePlan


@dataclass(frozen=True, slots=True)
class ZoneRecord:
    zid: int
    terrain: str
    ts: frozenset[Tile]
    open_set: frozenset[Tile]
    passable: frozenset[Tile]
    reach: frozenset[Tile] = frozenset()
    loot_zone: bool = False


@dataclass
class ZoneIndex:
    """Per-level walk targets and zone records. GatedStep builds it once, and every later
    step mutates that same instance in place. ``claims`` holds each level's claimed tiles,
    which a step loads into its cover index and writes back when it is done. ``hard_avoid``
    holds each level's gameplay footprints and approaches, which no border guard may take."""

    targets: dict[int, list[Tile]] = field(default_factory=dict)
    zone_records: dict[int, list[ZoneRecord]] = field(default_factory=dict)
    claims: dict[int, frozenset[Tile]] = field(default_factory=dict)
    hard_avoid: dict[int, frozenset[Tile]] = field(default_factory=dict)


def bare_record(zid: int, terrain: str, ts: frozenset[Tile], free: frozenset[Tile]) -> ZoneRecord:
    """The record of a zone the level pass skipped: its free tiles, nothing reached."""
    return ZoneRecord(zid=zid, terrain=terrain, ts=ts, open_set=free, passable=free)


def _level_records(
    pl: PlanLevel, placed: Mapping[int, PlacedZone], landings: Landings, targets: list[Tile]
) -> list[ZoneRecord]:
    zone_records: list[ZoneRecord] = []
    for zid, zone in sorted(pl.zones.items()):
        pz = placed[zid]
        reach = scatter_reach(pz.open_set - (zone.rim8 - zone.ent_bands), pz.prot)
        targets.extend(pz.approaches)
        targets.extend(r for r, _b, _o in zone.entrances)
        targets.extend(t for t in (landings.appr & zone.ts))
        zone_records.append(
            ZoneRecord(
                zid=zid,
                terrain=zone.terrain,
                ts=zone.ts,
                open_set=pz.open_set,
                passable=pz.passable,
                reach=frozenset(reach),
            )
        )
    return zone_records


def build_zone_index(
    plan: ZonePlan,
    placed: Mapping[int, Mapping[int, PlacedZone]],
    landings: Mapping[int, Landings],
) -> ZoneIndex:
    """One zone record per zone and the walk targets of every level, and each level's
    ``hard_avoid`` set for BorderStep."""
    index = ZoneIndex()
    for level, pl in plan.levels.items():
        targets: list[Tile] = []
        index.zone_records[level] = _level_records(pl, placed[level], landings[level], targets)
        index.targets[level] = targets
        index.hard_avoid[level] = frozenset[Tile]().union(
            *(pz.cells | frozenset(pz.approaches) for pz in placed[level].values())
        )
    return index
