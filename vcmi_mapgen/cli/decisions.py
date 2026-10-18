"""``decisions.json``: what the loot, treasure, quest, pocket and gameplay passes chose, with
tile coordinates, assembled from the results the steps provided."""

from __future__ import annotations

import json
from pathlib import Path
from typing import final

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState, PlacedObject, Tile
from vcmi_mapgen.core.pipeline import ProviderRegistry
from vcmi_mapgen.core.planning.pricing import CutoffPlace
from vcmi_mapgen.core.planning.zone_index import ZoneIndex
from vcmi_mapgen.core.steps.gameplay.result import GameplayResult, SlotRanking
from vcmi_mapgen.core.steps.gated.result import GatedResult
from vcmi_mapgen.core.steps.loot.result import LootResult, PocketDecision, QuestDecision
from vcmi_mapgen.core.steps.portal.result import PortalResult
from vcmi_mapgen.core.steps.terrain_gen.result import Segmentation
from vcmi_mapgen.core.steps.treasure.result import TreasureResult
from vcmi_mapgen.core.steps.vegetation.result import LootZones

type Record = dict[str, object]
type Anchors = dict[tuple[int, int, int], PlacedObject]


@final
class _Standing:
    """The object anchored at each tile of the finished map, named by the catalog."""

    def __init__(self, catalog: Catalog, map_state: MapState) -> None:
        self.catalog = catalog
        self.anchors: Anchors = {}
        for o in map_state.objs:
            self.anchors[o.level, o.x, o.y] = o

    def at(self, level: int, tile: Tile) -> Record | None:
        o = self.anchors.get((level, tile[0], tile[1]))
        if o is None:
            return None
        ident = self.catalog.identity_of(o.kind)
        return {"type": ident.type, "subtype": ident.subtype, "purpose": o.purpose}

    def tile(self, level: int, tile: Tile) -> Record:
        return {"tile": list(tile), "object": self.at(level, tile)}


def _tiles(tiles: frozenset[Tile] | tuple[Tile, ...]) -> list[list[int]]:
    return [list(t) for t in sorted(tiles)]


def _zone_tiles(ctx: ProviderRegistry, level: int, zid: int) -> frozenset[Tile]:
    index = ctx.get(ZoneIndex)
    if index is not None:
        for record in index.zone_records.get(level, ()):
            if record.zid == zid:
                return record.ts
    zone = ctx.get(Segmentation, Segmentation({}, {})).zones.get(level, {}).get(zid)
    return frozenset() if zone is None else zone.tiles_set


def _loot_zones(ctx: ProviderRegistry) -> Record:
    zones = ctx.get(LootZones, LootZones())
    access = ctx.get(GatedResult, GatedResult()).access
    levels: dict[str, object] = {}
    for level in sorted({*zones.candidates, *zones.levels}):
        drawn: list[Record] = []
        for zid in sorted(zones.on(level)):
            sealed = access.get(level, {}).get(zid)
            drawn.append(
                {
                    "zone": zid,
                    "tiles": _tiles(_zone_tiles(ctx, level, zid)),
                    "seal": "monolith" if zid in zones.monoliths_on(level) else "gate",
                    "sealed": sealed is not None,
                    "access": None
                    if sealed is None
                    else {
                        "entry": list(sealed.entry),
                        "footprint": _tiles(sealed.footprint),
                        "visit": _tiles(sealed.interactive),
                    },
                }
            )
        levels[str(level)] = {
            "candidates": sorted(zones.candidates.get(level, ())),
            "drawn": drawn,
        }
    return {"levels": levels}


def _place(standing: _Standing, level: int, zid: int, place: CutoffPlace) -> Record:
    price = place.price
    return {
        "zone": zid,
        "opener": str(place.opener),
        "price": {
            "days": price.effort.days,
            "guard": price.effort.guard,
            "total": price.effort.total,
            "band": price.band,
        },
        "prizes": [
            {**standing.tile(level, (o.x, o.y)), "purpose": o.purpose} for o in place.prizes
        ],
        "held": [standing.tile(level, h.tile) for h in place.held],
    }


def _treasure(ctx: ProviderRegistry, standing: _Standing) -> Record:
    out: dict[str, object] = {}
    for section, places in (
        ("treasure", ctx.get(TreasureResult, TreasureResult()).places),
        ("portal", ctx.get(PortalResult, PortalResult()).places),
    ):
        out[section] = {
            str(level): [_place(standing, level, zid, p) for zid, p in sorted(by_zone.items())]
            for level, by_zone in sorted(places.items())
        }
    return out


def _quest(standing: _Standing, q: QuestDecision) -> Record:
    return {
        "level": q.level,
        "hut": standing.tile(q.level, q.hut),
        "hut_zone": q.hut_zone,
        "artifact_at": standing.tile(q.level, q.artifact_tile),
        "artifact_zone": q.artifact_zone,
        "artifact": q.artifact,
    }


def _pocket(standing: _Standing, d: PocketDecision) -> Record:
    level = d.level
    guard = (
        None
        if d.guard is None
        else {**standing.tile(level, d.guard[0]), "creature_level": d.guard[1]}
    )
    ward = (
        None
        if d.ward is None
        else {**standing.tile(level, d.ward), "tier": d.ward_tier, "held": d.ward_held}
    )
    return {
        "level": level,
        "zone": d.zone,
        "planned": d.planned,
        "kind": d.kind,
        "tiles": _tiles(d.tiles),
        "mouth": _tiles(d.mouth),
        "outcome": str(d.outcome),
        "guard": guard,
        "ward": ward,
        "placed": [{**standing.tile(level, t), "purpose": p} for t, p in d.placed],
    }


def _slot(standing: _Standing, r: SlotRanking) -> Record:
    stood = r.stood
    return {
        "order": r.order,
        "family": r.family,
        "player": r.player,
        "band": r.band,
        "target": r.target,
        "guard": r.guard,
        "keys": list(r.keys),
        "ranked": [
            {
                "level": t.level,
                "tile": [t.x, t.y],
                "zone": t.zid,
                "values": dict(zip(r.keys, t.values, strict=False)),
            }
            for t in r.ranked
        ],
        "groups": [
            {
                "index": g.index,
                "tile": [g.x, g.y],
                "level": g.level,
                "zone": g.zid,
                "size": g.size,
                "values": dict(zip(r.keys, g.values, strict=False)),
                "outcome": g.outcome,
            }
            for g in r.groups
        ],
        "groups_seen": r.groups_seen,
        "stood": None
        if stood is None
        else {
            "level": stood.level,
            **standing.tile(stood.level, (stood.x, stood.y)),
            "family": stood.family,
            "guard": stood.guard,
            "footing": stood.footing,
            "smaller": stood.smaller,
            "group": stood.group,
            "strict": stood.strict,
            "centre": list(stood.centre),
            "rank": stood.rank,
            "tried_at": stood.tried_at,
        },
    }


def decisions_record(
    catalog: Catalog, ctx: ProviderRegistry, map_state: MapState
) -> dict[str, object]:
    """The loot zones, the cut-off treasure, the seer-hut quests, the pocket outcomes and the
    gameplay ranking of one run, read from what the steps provided. A run stopped early
    holds the sections it reached."""
    standing = _Standing(catalog, map_state)
    loot = ctx.get(LootResult, LootResult())
    gameplay = ctx.get(GameplayResult)
    ranking = () if gameplay is None else gameplay.ranking
    return {
        "loot_zones": _loot_zones(ctx),
        "treasure": _treasure(ctx, standing),
        "quests": [_quest(standing, q) for q in loot.quests],
        "pockets": [_pocket(standing, d) for d in loot.decisions],
        "gameplay": [_slot(standing, r) for r in ranking],
    }


def write_decisions(
    folder: Path, catalog: Catalog, ctx: ProviderRegistry, map_state: MapState
) -> Path:
    """Write ``decisions.json`` into the map's folder and return its path."""
    path = folder / "decisions.json"
    record = decisions_record(catalog, ctx, map_state)
    _ = path.write_text(json.dumps(record, indent=2) + "\n")
    return path
