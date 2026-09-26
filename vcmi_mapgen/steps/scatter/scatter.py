"""Unguarded resource piles over the finished open field.

Resource piles lying in the open along routes are always free. A guard only belongs at a
real chokepoint, never beside loot that sits in open terrain and can be walked around.
"""

import random
from collections.abc import Collection, Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass

from vcmi_mapgen import ontology as ON
from vcmi_mapgen.kit.geometry import edge_dist
from vcmi_mapgen.kit.topology import zone_gate_bands
from vcmi_mapgen.models import CoverIndex, Entrance, Identity, PlacedObject, Tile, Zone
from vcmi_mapgen.steps.gameplay import mines as PG
from vcmi_mapgen.steps.placement import PlaceSpec, PlaceTarget, place_one, web_dist

CAPS = {"RESOURCE_PILE": 16, "REWARD_PICKUP": 8}  # base floors; caps scale (scatter only --
# pocket guards/caches are deterministic, see place_pickups)
SCATTER_ART_SHARE = 0.15  # unguarded scatter: mostly LOOT (chests/campfires); the
# tiered random artifacts live behind cache guards instead

_NO_AVOID: frozenset[Tile] = frozenset()


@dataclass(frozen=True, slots=True)
class ScatterZone:
    ts: AbstractSet[Tile]
    zones: Mapping[int, Zone]
    zid: int
    terrain: str
    open_set: AbstractSet[Tile]
    prot: Collection[Tile]
    entrances: Sequence[Entrance] | None = None


@dataclass(frozen=True, slots=True)
class ScatterConfig:
    seed: int = 1
    bounds: tuple[int, int] | None = None
    cover: CoverIndex | None = None
    reach_in: set[Tile] | None = None
    used_in: set[Tile] | None = None
    avoid: AbstractSet[Tile] = _NO_AVOID


_DEFAULT_SCATTER_CONFIG = ScatterConfig()


def _stoch(rng: random.Random, x: float, cap: int) -> int:
    n = int(x) + (1 if rng.random() < x - int(x) else 0)
    return min(n, cap)


def _scatter_gate_dist(zone: ScatterZone, st: PG.TerrainStats) -> dict[Tile, int]:
    if zone.entrances is not None:  # isolation plan: gd measures from the
        bands = [(r, b) for r, b, _o in zone.entrances]  # planned narrow crossings
    else:
        bands = zone_gate_bands(zone.ts, zone.zones, zone.zid, open_frac=st.border_open_frac)
    return PG.gate_dist(zone.ts, set[Tile]().union(*(b for _r, b in bands)) if bands else set())


def place_scatter(
    zone: ScatterZone, config: ScatterConfig = _DEFAULT_SCATTER_CONFIG
) -> tuple[list[PlacedObject], set[Tile], set[Tile]]:
    """Unguarded scatter loot for one zone (resources/artifacts lying in the open along
    routes — user-mandated to always be free, never guarded, since it can just be walked
    around). Returns (objs, used, reach): `used` and `reach` (this zone's own BFS-reachable
    open tiles) are handed to `place_pocket_caches` so the global pocket pass knows which
    tiles this zone already spent on scatter and can treat the rest as this zone's share of
    the whole map's reachable field.

    Guarded pocket caches are NOT placed here — see `place_pocket_caches`, which must run
    once for the WHOLE map after every zone's scatter is done (a genuine pocket must be
    judged against true global passability, not one zone's reach alone)."""
    ts = zone.ts
    st = PG.mine_gameplay()[zone.terrain]
    rng = random.Random(config.seed ^ (zone.zid * 92821) ^ 0x9C4)
    area = len(ts)
    dens = {p: st.counts.get(p, 0) / max(st.tiles, 1) for p in PG.PICKUP_PURPOSES}

    n_res = _stoch(
        rng,
        dens["RESOURCE_PILE"] * area,
        PG.scaled_cap(CAPS["RESOURCE_PILE"], dens["RESOURCE_PILE"] * area),
    )

    dweb = web_dist(zone.open_set, zone.prot)
    reach = set(dweb) if config.reach_in is None else config.reach_in  # reachable open tiles only
    op = PG.openness(zone.open_set)
    ed = edge_dist(ts)
    gd = _scatter_gate_dist(zone, st)

    pool_res = ON.pool("RESOURCE_PILE", zone.terrain)

    objs: list[PlacedObject] = []
    used: set[Tile] = set() if config.used_in is None else config.used_in
    target = PlaceTarget(objs, used, reach, rng, st, bounds=config.bounds, cover=config.cover)

    # Open-field scatter is resource piles only — artifacts are reserved for pockets
    # and loot zones where a guard or gate makes them genuinely earned.
    def scatter(purpose: str, pool: Sequence[Identity], n: int, min_sep: int) -> None:
        if n <= 0:
            return
        wmap = PG.intensity_weights(reach, purpose, st, PG.Covariates(ed, gd, op))
        cands = sorted(reach)
        if not cands:  # zone has no reachable open tile
            return
        weights = [wmap[t] for t in cands]
        spec = PlaceSpec(purpose, pool, art_share=SCATTER_ART_SHARE)
        placed: list[Tile] = []
        for t in rng.choices(cands, weights=weights, k=60 * n):
            if len(placed) >= n:
                break
            if t in used or t in config.avoid:
                continue
            if any(max(abs(t[0] - q[0]), abs(t[1] - q[1])) < min_sep for q in placed):
                continue
            if place_one(target, spec, t[0], t[1]):
                placed.append(t)

    scatter("RESOURCE_PILE", pool_res, n_res, min_sep=3)
    return objs, used, reach
