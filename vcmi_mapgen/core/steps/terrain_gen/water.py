"""The topology surface form: the place graph laid out on all land first, then water drawn
from the place geometry by the fitted odds, steered to one corpus map's water target."""

import random
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from typing import cast

import numpy as np

from vcmi_mapgen.core.grid.paths import geodesic_path
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.priors.water import WaterPriors, WaterTarget
from vcmi_mapgen.core.reading.places import PlaceRole
from vcmi_mapgen.core.reading.water import (
    STATIC,
    Floats,
    Labels,
    Mask,
    edge_water_share,
    neighbour_features,
    static_features,
    water_places,
)
from vcmi_mapgen.core.steps.terrain_gen.coastline import Coastline, target_gap
from vcmi_mapgen.core.steps.terrain_gen.gate_sites import gate_anchor_points, gate_site_tiles
from vcmi_mapgen.core.steps.terrain_gen.layout import Layout, lay_out
from vcmi_mapgen.core.steps.terrain_gen.model import TerrainOptions
from vcmi_mapgen.core.steps.terrain_gen.place_graph import PlaceGraph, draw_graph
from vcmi_mapgen.core.steps.terrain_gen.streams import stream

SWEEPS = 80
SHARE_GAIN = 4.0
EDGE_GAIN = 6.0
EDGE_SCALE = 3.0
STRAIT_HALF = 1
ANCHOR_RING = 3.0
ANCHOR_PULL = 8.0
MIN_WATER = 0.02
NO_WATER = WaterTarget(0.0, 0.0, 1)


@dataclass(frozen=True, slots=True)
class Pins:
    """The tiles the sampler keeps land, the tiles it keeps water, and the pull away from
    water on every tile."""

    protect: Mask
    forced: Mask
    pull: Floats


def draw_target(targets: Sequence[WaterTarget], rng: random.Random) -> WaterTarget:
    """One corpus map's water target, or no water without targets."""
    return rng.choice(targets) if targets else NO_WATER


def masses_of(graph: PlaceGraph, k: int, rng: random.Random) -> list[int]:
    """The land mass of each planned place. The homes seed the first masses, and the mass
    with the least area grows by a random neighbour until every place has one. A place no
    mass reaches joins mass 0."""
    n = len(graph.roles)
    nbrs: dict[int, set[int]] = {i: set() for i in range(n)}
    for a, b in graph.edges:
        nbrs[a].add(b)
        nbrs[b].add(a)
    homes = [i for i, r in enumerate(graph.roles) if r is PlaceRole.HOME]
    rest = [i for i in range(n) if i not in homes]
    extra = rng.sample(rest, min(len(rest), k - len(homes))) if len(homes) < k else []
    seeds = homes[:k] + extra
    mass = {s: j for j, s in enumerate(seeds)}
    area = [graph.sizes[s] for s in seeds]
    while len(mass) < n:
        frontier = [
            (area[mass[p]], p, q) for p in sorted(mass) for q in sorted(nbrs[p]) if q not in mass
        ]
        if not frontier:
            break
        least = min(f[0] for f in frontier)
        _, p, q = rng.choice([f for f in frontier if f[0] == least])
        mass[q] = mass[p]
        area[mass[p]] += graph.sizes[q]
    return [mass.get(i, 0) for i in range(n)]


def strait_tiles(mass_grid: Labels) -> Mask:
    """The tiles with a Chebyshev neighbour on another mass."""
    h, w = mass_grid.shape
    r = STRAIT_HALF
    pad = np.pad(mass_grid, r, mode="edge")
    cut = np.zeros((h, w), dtype=np.bool_)
    for dy in range(2 * r + 1):
        for dx in range(2 * r + 1):
            cut |= cast("Mask", pad[dy : dy + h, dx : dx + w] != mass_grid)
    return cut


def _widen(mask: Mask) -> Mask:
    h, w = mask.shape
    pad = np.pad(mask, 1)
    out = np.zeros((h, w), dtype=np.bool_)
    for dy in range(3):
        for dx in range(3):
            out |= pad[dy : dy + h, dx : dx + w]
    return out


def bridge_tiles(
    label: Labels,
    anchors: Sequence[tuple[int, int]],
    edges: Iterable[tuple[int, int]],
    mass: Sequence[int],
    forced: Mask,
) -> Mask:
    """The land every planned pair on one mass keeps: the shortest walk between the two
    anchors inside the pair's places and off ``forced``, widened by one tile inside them."""
    out = np.zeros(label.shape, dtype=np.bool_)
    for a, b in sorted(edges):
        if mass[a] != mass[b]:
            continue
        inside = cast("Mask", ((label == a) | (label == b)) & ~forced)
        ys, xs = np.nonzero(inside)
        tiles = set(
            zip(cast("list[int]", xs.tolist()), cast("list[int]", ys.tolist()), strict=True)
        )
        walk = np.zeros(label.shape, dtype=np.bool_)
        for x, y in geodesic_path(anchors[a], anchors[b], tiles):
            walk[y, x] = True
        out |= _widen(walk) & inside
    return out


def _grid(h: int, w: int) -> tuple[Labels, Labels]:
    ys = np.repeat(np.arange(h, dtype=np.int64), w).reshape(h, w)
    xs = np.tile(np.arange(w, dtype=np.int64), h).reshape(h, w)
    return ys, xs


def sample_water(
    static: Floats, odds: WaterPriors, target: WaterTarget, pins: Pins, rng: random.Random
) -> Mask:
    """The water mask by Gibbs sweeps over the fitted odds in four parity passes, with
    the protected tiles kept land and the forced tiles kept water. After each sweep two
    multipliers move the odds toward the target share and edge share."""
    h, w = pins.pull.shape
    np_rng = np.random.default_rng(rng.getrandbits(63))
    ys, xs = _grid(h, w)
    ring = np.minimum(np.minimum(xs, ys), np.minimum(w - 1 - xs, h - 1 - ys))
    edge: Floats = np.exp(-ring / EDGE_SCALE)
    pull = ANCHOR_PULL * pins.pull
    start = cast("Floats", static @ np.array(odds.static_beta)).reshape(h, w) - pull
    field = cast("Floats", static @ np.array(odds.beta[:STATIC])).reshape(h, w) - pull
    b4, bd = odds.beta[STATIC], odds.beta[STATIC + 1]
    parities = [cast("Mask", (ys % 2 == py) & (xs % 2 == px)) for py in (0, 1) for px in (0, 1)]
    water = start > np.quantile(start, 1 - target.share)
    water[pins.protect] = False
    water[pins.forced] = True
    bias, lam = 0.0, 0.0
    for _ in range(SWEEPS):
        base = field + bias + lam * edge
        for parity in parities:
            nb = neighbour_features(water)
            z = base + b4 * nb[:, :1].reshape(h, w) + bd * nb[:, 1:].reshape(h, w)
            draw = np_rng.random((h, w)) < 1 / (1 + np.exp(-z))
            water = np.where(parity, draw, water)
            water[pins.protect] = False
            water[pins.forced] = True
        bias += SHARE_GAIN * (target.share - float(np.mean(water)))
        lam += EDGE_GAIN * (target.edge - edge_water_share(water))
    return water


def _pins(
    graph: PlaceGraph,
    layout: Layout,
    mass: tuple[Sequence[int], Labels, int],
    gates: Sequence[tuple[int, int]],
) -> Pins:
    masses, mass_grid, k = mass
    h, w = mass_grid.shape
    gy, gx = _grid(h, w)
    pull: Floats = np.zeros((h, w))
    protect = np.zeros((h, w), dtype=np.bool_)
    for x, y in layout.anchors:
        pull = np.maximum(pull, np.exp(-np.hypot(gx - x, gy - y) / ANCHOR_RING))
        protect[y, x] = True
    forced = strait_tiles(mass_grid) if k > 1 else np.zeros((h, w), dtype=np.bool_)
    protect &= ~forced
    label = np.array(layout.label, dtype=np.int64)
    protect |= bridge_tiles(label, layout.anchors, graph.edges, masses, forced)
    for x, y in gates:
        protect[y, x] = True
        forced[y, x] = False
    return Pins(protect, forced, pull)


class TopologyForm:
    """The place graph and its layout on all land, then water drawn around the places."""

    def form(self, priors: Priors, seed: int, options: TerrainOptions) -> Coastline:
        rng = stream(seed, "water")
        target = draw_target(priors.water.targets, rng)
        stats, size = priors.places[0], options.size
        land = [[True] * size for _ in range(size)]
        n_land = round(size * size * (1 - target.share))
        graph = draw_graph(stats, options.players, n_land, stream(seed, "places"))
        layout = lay_out(land, graph, target_gap(stats), stream(seed, "layout"))
        if target.share < MIN_WATER:
            return Coastline(graph, layout, (_line(target, np.zeros((size, size), np.bool_)),))
        mass = masses_of(graph, max(1, target.masses), rng)
        n = len(graph.roles)
        mass_grid = np.array(
            [[mass[z] if 0 <= z < n else 0 for z in row] for row in layout.label], dtype=np.int64
        )
        homes = [layout.anchors[i] for i, r in enumerate(graph.roles) if r is PlaceRole.HOME]
        places = water_places(layout.label, mass_grid)
        static = static_features((size, size), places, homes, target.edge)
        gates = gate_site_tiles(gate_anchor_points(size, size, seed), size)
        pins = _pins(
            graph,
            layout,
            (mass, mass_grid, target.masses),
            list(gates) if options.subterrain else [],
        )
        water = sample_water(static, priors.water, target, pins, rng)
        wet = cast("list[list[bool]]", water.tolist())
        label = [
            [-1 if w else z for w, z in zip(wr, lr, strict=True)]
            for wr, lr in zip(wet, layout.label, strict=True)
        ]
        return Coastline(graph, replace(layout, label=label), (_line(target, water),))


def _line(target: WaterTarget, water: Mask) -> str:
    return (
        f"  water: target share {target.share:.2f}, edge {target.edge:.2f}, "
        + f"{target.masses} masses; drawn share {float(np.mean(water)):.2f}, "
        + f"edge {edge_water_share(water):.2f}"
    )
