"""One level's water decoration: rocks, reefs and kelp drawn at the corpus kind odds until
they block the map's share of the water. A decoration never blocks a tile beside a cell a
hero steps on, and never splits the sea."""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass

from vcmi_mapgen.core.model import Identity, PlacedObject, Tile
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.placement import footprint as FP

TRIES_PER_TILE = 8
NEIGHBOURS = tuple((dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy)


@dataclass(frozen=True, slots=True)
class SeaLevel:
    """What one level's dressing reads: its water tiles, the tiles earlier objects cover,
    block or claimed, the cells a hero steps on, and the share of water to block."""

    level: int
    water: frozenset[Tile]
    taken: frozenset[Tile]
    blocked: frozenset[Tile]
    visits: frozenset[Tile]
    rate: float


def dress_level(
    lv: SeaLevel, kinds: Sequence[tuple[Identity, float]], rng: random.Random
) -> list[PlacedObject]:
    """Water decorations for one level, drawn by kind weight on random water tiles, until
    they block ``rate`` of the water or the tries run out."""
    if not lv.water or not kinds or lv.rate <= 0:
        return []
    tiles = sorted(lv.water)
    goal = round(lv.rate * len(tiles))
    near = {(x + dx, y + dy) for x, y in lv.visits for dx, dy in (*NEIGHBOURS, (0, 0))}
    taken = set(lv.taken)
    passable = set(lv.water) - lv.blocked
    idents = [k for k, _w in kinds]
    weights = [w for _k, w in kinds]
    out: list[PlacedObject] = []
    done = 0
    for _ in range(TRIES_PER_TILE * len(tiles)):
        if done >= goal:
            break
        ident = rng.choices(idents, weights)[0]
        x, y = rng.choice(tiles)
        cells = list(FP.anchored_cells(ident.footprint, x, y))
        if any((cx, cy) not in lv.water or (cx, cy) in taken for cx, cy, _b in cells):
            continue
        solid = {(cx, cy) for cx, cy, b in cells if b}
        if solid & near or not keeps_sea(passable, solid):
            continue
        out.append(PlacedObject.at(ident, (x, y), level=lv.level, purpose=Purpose.DECORATION))
        taken.update((cx, cy) for cx, cy, _b in cells)
        passable -= solid
        done += len(solid)
    return out


def keeps_sea(passable: set[Tile], solid: set[Tile]) -> bool:
    """Whether blocking ``solid`` leaves every passable neighbour of it joined to the others
    inside the box around it, so no sea splits."""
    if not solid:
        return True
    xs = [x for x, _y in solid]
    ys = [y for _x, y in solid]
    x0, x1, y0, y1 = min(xs) - 1, max(xs) + 1, min(ys) - 1, max(ys) + 1
    box = {
        (x, y)
        for x in range(x0, x1 + 1)
        for y in range(y0, y1 + 1)
        if (x, y) in passable and (x, y) not in solid
    }
    ring = {(x + dx, y + dy) for x, y in solid for dx, dy in NEIGHBOURS} & box
    if not ring:
        return True
    start = next(iter(ring))
    seen = {start}
    stack = [start]
    while stack:
        x, y = stack.pop()
        for dx, dy in NEIGHBOURS:
            t = (x + dx, y + dy)
            if t in box and t not in seen:
                seen.add(t)
                stack.append(t)
    return ring <= seen
