"""One level's border guards: entrance guards first, then a guard on every crossing left
open."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import Entrance, PlacedObject, PlacementRule, Tile
from vcmi_mapgen.core.planning.zone_index import ZoneRecord
from vcmi_mapgen.core.steps.border.crossings import CrossingRules, LevelGrid, guard_crossings
from vcmi_mapgen.core.steps.border.entrances import EntranceField, guard_entrances


@dataclass(frozen=True, slots=True)
class BorderLevel:
    """What one level's guarding reads: its terrain and zones, its entrance plan, its zone
    records, the zones that host a player town, the tiles no guard may stand on, and the rules
    every guard must pass."""

    grid: LevelGrid
    entrance_plan: Mapping[int, Sequence[Entrance]]
    records: Sequence[ZoneRecord]
    home_zids: frozenset[int]
    avoid: frozenset[Tile]
    rules: Sequence[PlacementRule] = ()


@dataclass(frozen=True, slots=True)
class Guarded:
    """One level's new guards in placement order, every tile a guard stands on, and the
    crossings no guard could take."""

    objs: tuple[PlacedObject, ...]
    guard_tiles: frozenset[Tile]
    n_open: int


def _loot_tiles(zone_records: Sequence[ZoneRecord]) -> set[Tile]:
    loot_ts: set[Tile] = set()
    for zr in zone_records:
        if zr.loot_zone:
            loot_ts |= zr.ts
    return loot_ts


def _entrance_bands(entrance_plan: Mapping[int, Sequence[Entrance]]) -> set[Tile]:
    bands: set[Tile] = set()
    for ents in entrance_plan.values():
        for _r, b, _o in ents:
            bands |= b
    return bands


def guard_level(
    catalog: Catalog, lv: BorderLevel, level_objs: Sequence[PlacedObject], seed: int
) -> Guarded:
    """Guard most planned entrances outside a loot zone, then every crossing still open
    outside the entrance bands and the loot zones. ``level_objs`` is left unchanged."""
    objs = list(level_objs)
    field = EntranceField(
        plan=lv.entrance_plan,
        zone_tiles={zr.zid: zr.ts for zr in lv.records},
        home_zids=lv.home_zids,
        skip_zids={zr.zid for zr in lv.records if zr.loot_zone},
        avoid=lv.avoid,
        rules=lv.rules,
    )
    ent_objs = guard_entrances(catalog, field, objs, seed, lv.grid.level)
    objs.extend(ent_objs)
    rules = CrossingRules(
        _entrance_bands(lv.entrance_plan),
        lv.avoid,
        skip_tiles=_loot_tiles(lv.records),
        placement=lv.rules,
    )
    new_objs, guard_tiles, n_open = guard_crossings(catalog, lv.grid, rules, objs, seed)
    guard_tiles |= {(o.x, o.y) for o in ent_objs}
    return Guarded((*ent_objs, *new_objs), frozenset(guard_tiles), n_open)
