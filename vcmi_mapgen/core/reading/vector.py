"""One map's reading vector (map-math 8): the scalar readings the ``readings`` subcommand
compares between generated maps and the corpus, all read from the surface level, with the
territory readings of slice 4 of ``docs/plans/territories-and-doors.md``."""

import statistics
from collections.abc import Mapping, Sequence

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState, Tile
from vcmi_mapgen.core.priors.places import PlaceContent
from vcmi_mapgen.core.reading.borders import AdjacencyKind
from vcmi_mapgen.core.reading.content import UNREACHED, hops, place_content
from vcmi_mapgen.core.reading.ground import Ground, TownKey, read_ground
from vcmi_mapgen.core.reading.measures import home_separation, raw_cut_share, soft_borders
from vcmi_mapgen.core.reading.palette import palette_regions, same_share
from vcmi_mapgen.core.reading.places import InferredPlaces, PlaceRole, read_places
from vcmi_mapgen.core.reading.territories import (
    SHARE_TILES,
    TerritoryReading,
    read_territories,
    territory_reading,
)

HOP_CAP = 4
FAR_HOP = 2
LEVEL = 0

type Vector = dict[str, float]


def _share(part: int, whole: int) -> float | None:
    return part / whole if whole else None


def _put(out: Vector, key: str, value: float | None) -> None:
    if value is not None:
        out[key] = value


def border_shares(inferred: InferredPlaces) -> dict[str, float]:
    """The share of place pairs of each adjacency kind, keyed ``<kind>_share``."""
    kinds = list(inferred.adjacency.values())
    if not kinds:
        return {}
    return {f"{k.value}_share": kinds.count(k) / len(kinds) for k in AdjacencyKind}


def by_hop(rows: Sequence[PlaceContent]) -> dict[str, float]:
    """The reward value per tile and the mean guard level of the places at each hop from the
    nearest home, hops capped at ``HOP_CAP`` and unreached places left out."""
    out: dict[str, float] = {}
    for h in range(HOP_CAP + 1):
        group = [c for c in rows if c.hop != UNREACHED and min(c.hop, HOP_CAP) == h]
        area = sum(c.area for c in group)
        if area:
            out[f"value_hop{h}"] = sum(c.value for c in group) / area
        levels = [lv for c in group for lv in c.guards]
        if levels:
            out[f"guard_hop{h}"] = statistics.mean(levels)
    return out


def _mean(values: Sequence[int]) -> float | None:
    return statistics.mean(values) if values else None


def _median(values: Sequence[int]) -> float | None:
    return float(statistics.median(values)) if values else None


def territory_vector(reading: TerritoryReading) -> Vector:
    """The mean zones per player and per neutral territory, the mean doors per bordering
    pair, and the median door level out of a player territory and between neutral ones.
    Then the territory count, the loops, the mean doors between two close territories a
    door path joins, the share of close pairs more than ``FAR_HOP`` doors apart or cut
    off, and the share no door or link joins. Last, ``door_share_d<n>`` for each distance
    ``n`` from 2 to ``SHARE_TILES`` between two territories' nearest tiles: the share of the
    pairs that far apart a door or a link joins. Then ``home_area_ratio``, the largest
    player territory's tiles over the smallest's when two or more read, and
    ``home_area_share``, the mean player territory's share of every territory's tiles."""
    out: Vector = {}
    _put(out, "zones_player_terr", _mean(reading.player_zones))
    _put(out, "zones_neutral_terr", _mean(reading.neutral_zones))
    _put(out, "doors_per_pair", _mean(reading.pair_doors))
    _put(out, "door_level_player", _median(reading.player_door_levels))
    _put(out, "door_level_neutral", _median(reading.neutral_door_levels))
    if reading.territories:
        out["territory_count"] = float(reading.territories)
        out["territory_loops"] = float(reading.loops)
    reached = [h for h in reading.close_hops if h is not None]
    _put(out, "close_pair_hops", statistics.mean(reached) if reached else None)
    far = sum(1 for h in reading.close_hops if h is None or h > FAR_HOP)
    _put(out, "close_pair_far", _share(far, len(reading.close_hops)))
    walled = reading.close_joined.count(False)
    _put(out, "close_pair_walled", _share(walled, len(reading.close_joined)))
    for d in range(2, SHARE_TILES + 1):
        at = [joined for dist, joined in reading.near if dist == d]
        _put(out, f"door_share_d{d}", _share(at.count(True), len(at)))
    homes = reading.player_areas
    if len(homes) > 1 and min(homes):
        out["home_area_ratio"] = max(homes) / min(homes)
    total = sum(homes) + sum(reading.neutral_areas)
    if homes and total:
        out["home_area_share"] = statistics.mean(homes) / total
    return out


def _content(
    catalog: Catalog, map_state: MapState, inferred: InferredPlaces
) -> tuple[PlaceContent, ...]:
    homes = [p for p, place in enumerate(inferred.places) if place.role == PlaceRole.HOME]
    walk = [pq for pq, kind in inferred.adjacency.items() if kind != AdjacencyKind.CLOSED]
    roles = {p: place.role.value for p, place in enumerate(inferred.places)}
    objs = map_state.objs_by_level([LEVEL])[LEVEL]
    return place_content(catalog, objs, inferred.labels, roles, hops(walk, homes))


def ground_vector(
    ground: Ground,
    inferred: InferredPlaces,
    content: Sequence[PlaceContent],
    roads: Mapping[Tile, int],
) -> Vector:
    """The readings of one read level."""
    land, walk = len(ground.land), len(ground.walk)
    dominant = {p: int(place.dominant) for p, place in enumerate(inferred.places)}
    pairs = list(inferred.borders)
    sep = home_separation(ground, inferred)
    guards = sum(len(c.guards) + c.fixed for c in content)
    out: Vector = {"palette_regions": float(palette_regions(dominant, pairs))}
    _put(out, "same_share", same_share(dominant, pairs))
    _put(out, "raw_cut", raw_cut_share(ground, inferred, soft_borders(ground, inferred)))
    out.update(border_shares(inferred))
    _put(out, "walk_share", _share(walk, land))
    _put(out, "zoc_share", _share(len(ground.zoc), walk))
    _put(out, "rewards_per_100_walk", _share(100 * len(ground.rewards), walk))
    _put(out, "guards_per_100_land", _share(100 * guards, land))
    _put(out, "home_separation", statistics.median(sep) if sep else None)
    out.update(by_hop(content))
    _put(out, "road_share", _share(sum(1 for t in roads if t in ground.land), walk))
    return out


def map_vector(catalog: Catalog, map_state: MapState, owners: Mapping[TownKey, int]) -> Vector:
    """The surface readings of ``map_state``, whose player towns ``owners`` names. A map with
    no surface land reads as an empty vector."""
    ground = read_ground(catalog, map_state, LEVEL)
    if ground is None or not ground.land:
        return {}
    inferred = read_places(ground, owners)
    content = _content(catalog, map_state, inferred)
    out = ground_vector(ground, inferred, content, map_state.roads.get(LEVEL, {}))
    territories = read_territories(catalog, map_state, LEVEL, owners)
    if territories is not None:
        out.update(territory_vector(territory_reading(territories)))
    return out
