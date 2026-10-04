"""One map's reading vector (map-math 8): the scalar readings the ``readings`` subcommand
compares between generated maps and the corpus, all read from the surface level."""

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

HOP_CAP = 4
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
    return ground_vector(ground, inferred, content, map_state.roads.get(LEVEL, {}))
