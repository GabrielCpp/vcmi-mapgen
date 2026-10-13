"""Subterranean Gate sites: anchor points spread over the map, each carved open on the
surface and underground, with an underground tunnel to the nearest cavern, and the gates
planned on them before the underground draws its doors."""

import collections
import math
import random
from collections.abc import Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass

from vcmi_mapgen.core.grid.segment import ZoneLabel
from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.steps.terrain_gen.macro import carve_corridor

type Gate = tuple[Tile, tuple[int, int]]


@dataclass(frozen=True, slots=True)
class _GateLayout:
    n_sites: int = 8
    margin: int = 8
    pad: int = 4


def gate_anchor_points(W: int, H: int, seed: int, layout: _GateLayout | None = None) -> list[Tile]:
    lay = _GateLayout() if layout is None else layout
    n_sites, margin, pad = lay.n_sites, lay.margin, lay.pad
    rng = random.Random(seed ^ 0xA7E5)
    cols = max(1, round(math.pow(n_sites, 0.5)))
    rows = -(-n_sites // cols)
    lo, hi_x, hi_y = margin, W - margin, H - margin
    anchors: list[Tile] = []
    for i in range(n_sites):
        gx = lo + (hi_x - lo) * ((i % cols) + 0.5) / cols
        gy = lo + (hi_y - lo) * ((i // cols) + 0.5) / rows
        ax = min(W - 2 - pad, max(margin, int(gx) + rng.randint(-3, 3)))
        ay = min(H - 3 - pad, max(margin, int(gy) + rng.randint(-3, 3)))
        anchors.append((ax, ay))
    return anchors


def _gate_site_cells(ax: int, ay: int, pad: int = 4) -> set[Tile]:
    r2 = (pad + 0.5) ** 2
    return {
        (ax + dx, ay + dy)
        for dy in range(-pad, pad + 1)
        for dx in range(-pad, pad + 1)
        if dx * dx + dy * dy <= r2
    }


def gate_site_tiles(anchors: list[Tile], size: int, pad: int = 4) -> frozenset[Tile]:
    """The on-map tiles of every gate site disk around ``anchors``."""
    return frozenset(
        (x, y)
        for ax, ay in anchors
        for x, y in _gate_site_cells(ax, ay, pad)
        if 0 <= x < size and 0 <= y < size
    )


def carve_gate_sites(
    grid0: list[list[int]],
    grid1: list[list[int]] | None,
    anchors: list[Tile],
    seed: int,
    pad: int = 4,
) -> set[Tile]:
    H = len(grid0)
    W = len(grid0[0])
    land0 = collections.Counter(
        grid0[y][x] for y in range(H) for x in range(W) if grid0[y][x] != Terrain.WATER
    )
    fill0 = land0.most_common(1)[0][0] if land0 else 2
    protect1: set[Tile] = set()
    if grid1 is None:
        for ax, ay in anchors:
            for x, y in _gate_site_cells(ax, ay, pad):
                if 0 <= x < W and 0 <= y < H:
                    grid0[y][x] = fill0
        return protect1

    land1 = collections.Counter(
        grid1[y][x] for y in range(H) for x in range(W) if Terrain(grid1[y][x]).is_land
    )
    fill1 = land1.most_common(1)[0][0] if land1 else 6
    land1_before = {(x, y) for y in range(H) for x in range(W) if Terrain(grid1[y][x]).is_land}
    rng = random.Random(seed ^ 0xC0DE)
    for ax, ay in anchors:
        for x, y in _gate_site_cells(ax, ay, pad):
            if 0 <= x < W and 0 <= y < H:
                grid0[y][x] = fill0
                grid1[y][x] = fill1
        if land1_before:
            tx, ty = min(land1_before, key=lambda t: (t[0] - ax) ** 2 + (t[1] - ay) ** 2)
            _tunnel_underground(grid1, ((ax, ay), (tx, ty)), fill1, rng, protect1)
        land1_before.add((ax, ay))
    return protect1


def _tunnel_underground(
    grid1: list[list[int]],
    span: tuple[Tile, Tile],
    fill1: int,
    rng: random.Random,
    protect1: set[Tile],
) -> None:
    H = len(grid1)
    W = len(grid1[0])
    land_bool = [[Terrain(grid1[y][x]).is_land for x in range(W)] for y in range(H)]
    carve_corridor(land_bool, span, rng, half_w=1, protect=protect1)
    for y in range(H):
        for x in range(W):
            if land_bool[y][x] and Terrain(grid1[y][x]).is_barrier:
                grid1[y][x] = fill1


@dataclass(frozen=True, slots=True)
class GateGround:
    """Where a planned gate may stand: the place labels on the surface and underground,
    the front tiles no gate covers, and the room a gate keeps clear, as offsets from its
    anchor."""

    labels: tuple[ZoneLabel, ZoneLabel]
    fronts: AbstractSet[Tile]
    cells: Sequence[Tile]

    def zones(self, anchor: Tile) -> tuple[int, int] | None:
        """The zone pair every cell of a gate's room at ``anchor`` lies in, None when a cell
        falls off a place on either level, on a front, or in another zone."""
        label0, label1 = self.labels
        out: tuple[int, int] | None = None
        for dx, dy in self.cells:
            x, y = anchor[0] + dx, anchor[1] + dy
            if not (0 <= y < len(label0) and 0 <= x < len(label0[y])) or (x, y) in self.fronts:
                return None
            zones = (label0[y][x], label1[y][x])
            if min(zones) < 0 or (out is not None and zones != out):
                return None
            out = zones
        return out


def plan_gates(
    anchors: Sequence[Tile],
    ground: GateGround,
    spacing: tuple[int, float],
    rng: random.Random,
) -> list[Gate]:
    """Up to ``spacing[0]`` gate anchors, each with its zone on the surface and underground.
    The carved ``anchors`` go first in a drawn order, then every other tile in a place on
    both levels, also in a drawn order. A gate stands where ``ground`` gives its room one
    zone pair. Each zone on either level holds at most one gate, and no two gates sit
    closer than ``spacing[1]``."""
    count, min_gap = spacing
    label0, label1 = ground.labels
    first = list(anchors)
    rng.shuffle(first)
    rest = sorted(
        (x, y)
        for y, row in enumerate(label0)
        for x, z in enumerate(row)
        if z >= 0 and label1[y][x] >= 0
    )
    rng.shuffle(rest)
    out: list[Gate] = []
    used: tuple[set[int], set[int]] = (set(), set())
    for t in (*first, *rest):
        if len(out) >= count:
            break
        zones = ground.zones(t)
        if zones is None or zones[0] in used[0] or zones[1] in used[1]:
            continue
        if any(math.dist(t, g) < min_gap for g, _ in out):
            continue
        used[0].add(zones[0])
        used[1].add(zones[1])
        out.append((t, zones))
    return out
