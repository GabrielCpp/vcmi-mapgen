"""Accent landmarks: every accent patch of ``LANDMARK_FLOOR`` tiles or more holds one gold
mine, abandoned mine, permanent stat building or dwelling, its entrance on the patch. The
first kind is drawn by the corpus patch mix, and the others follow in list order when the
patch has no room for it. The patch the homes reach last holds a dragon dwelling instead,
guarded at the top level."""

from __future__ import annotations

import random
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import final

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import Identity, PlacedObject, Tile
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.placement.guards import Fit
from vcmi_mapgen.core.placement.site import ZoneSite, door_cells
from vcmi_mapgen.core.reading.effort import Effort
from vcmi_mapgen.core.reading.paint import Accent
from vcmi_mapgen.core.reading.routes import Spot
from vcmi_mapgen.core.steps.gameplay.economy import GOLD
from vcmi_mapgen.core.steps.gameplay.fallback import smaller

LANDMARK_FLOOR = 20
LANDMARK_SALT = 0x1A4D
TOP_TIER = 7


@dataclass(frozen=True, slots=True)
class LandmarkKind:
    """One kind of landmark: its name, the purpose it is placed for and its corpus weight."""

    name: str
    purpose: Purpose
    weight: int


GOLD_MINE = LandmarkKind("gold", Purpose.MINE, 83)
ABANDONED_MINE = LandmarkKind("abandoned", Purpose.MINE, 83)
STAT_BUILDING = LandmarkKind("stat", Purpose.STAT_PERMANENT, 132)
DWELLING = LandmarkKind("dwelling", Purpose.DWELLING, 112)
KINDS = (GOLD_MINE, ABANDONED_MINE, STAT_BUILDING, DWELLING)


def kind_order(rng: random.Random, kinds: Sequence[LandmarkKind] = KINDS) -> list[LandmarkKind]:
    """One kind drawn by weight, then the others in list order."""
    first = rng.choices(list(kinds), weights=[k.weight for k in kinds])[0]
    return [first, *(k for k in kinds if k != first)]


def above_top_tier(catalog: Catalog, ident: Identity) -> bool:
    """Whether ``ident`` is a dwelling that recruits above the top guard level."""
    return (catalog.dwelling_level(ident.kind) or 0) > TOP_TIER


def landmark_pool(catalog: Catalog, kind: LandmarkKind, terrain: str) -> list[Identity]:
    """The identities of ``kind`` on ``terrain``, without the dwellings above the top tier."""
    if kind == GOLD_MINE:
        return catalog.mines_by_resource(terrain).get(GOLD, [])
    if kind == ABANDONED_MINE:
        return catalog.abandoned_mines(terrain)
    return [i for i in catalog.candidates(kind.purpose, terrain) if not above_top_tier(catalog, i)]


def dragon_pool(catalog: Catalog, terrain: str) -> list[Identity]:
    """The dwellings on ``terrain`` that recruit above the top tier."""
    return [i for i in catalog.candidates(Purpose.DWELLING, terrain) if above_top_tier(catalog, i)]


def dragon_order(
    levels: Mapping[int, Sequence[Accent]], effort: Callable[[Spot], Effort | None]
) -> list[tuple[int, Accent]]:
    """The patches at or above the floor that a home reaches, the costliest to reach first,
    each priced at its cheapest tile, the larger patch first on a tie."""
    ranked: list[tuple[tuple[int, int, Tile], int, Accent]] = []
    for level, patches in sorted(levels.items()):
        for patch in patches:
            if patch.size < LANDMARK_FLOOR:
                continue
            found = [e.total for x, y in patch.tiles if (e := effort(Spot(level, x, y)))]
            if found:
                x, y = min(patch.tiles)
                ranked.append(((-min(found), -patch.size, (x, y)), level, patch))
    return [(level, patch) for _, level, patch in sorted(ranked, key=lambda r: (r[0], r[1]))]


def patch_rng(seed: int, level: int, patch: Accent) -> random.Random:
    """The draw of one patch, the same whichever zone order reaches it."""
    x, y = min(patch.tiles)
    return random.Random(seed ^ LANDMARK_SALT ^ (level * 7919) ^ (x * 104729 + y))


def spot_order(tiles: frozenset[Tile], ident: Identity) -> list[Tile]:
    """The patch tiles nearest the anchor that centres ``ident`` on the patch first."""
    cx = sum(x for x, _ in tiles) / len(tiles) + (ident.footprint.width - 1) / 2.0
    cy = sum(y for _, y in tiles) / len(tiles) + (ident.footprint.height - 1) / 2.0
    return sorted(tiles, key=lambda t: ((t[0] - cx) ** 2 + (t[1] - cy) ** 2, t))


@final
@dataclass(frozen=True, slots=True)
class PatchFooting:
    """The zone footing with every door cell of the body on the patch."""

    patch: frozenset[Tile]
    mine: bool = False

    def anchors(self, site: ZoneSite, ident: Identity) -> list[Tile]:
        fw, fh = ident.footprint.width, ident.footprint.height
        near = {(x + dx, y + dy) for x, y in self.patch for dx in range(fw) for dy in range(fh)}
        return sorted(near & site.ts)

    def fit(self, site: ZoneSite, ident: Identity, anchor: Tile) -> Fit | None:
        if not all(t in self.patch for t in door_cells(ident.footprint, anchor)):
            return None
        return site.fit(ident, anchor, self.mine)


def place_landmark(
    site: ZoneSite, patch: Accent, terrain: str, rng: random.Random
) -> PlacedObject | None:
    """Stand one landmark on ``patch``, whose ground is ``terrain``: the drawn kind first, a
    smaller object of the same kind next, then the next kind."""
    for kind in kind_order(rng):
        pool = landmark_pool(site.catalog, kind, terrain)
        if not pool:
            continue
        footing = PatchFooting(patch.tiles, kind.purpose == Purpose.MINE)
        first = rng.choice(pool)
        for ident in (first, *smaller(site, pool, first)):
            obj = site.place(kind.purpose, ident, spot_order(patch.tiles, ident), footing)
            if obj is not None:
                return obj
    return None


def stand_dragon(
    site: ZoneSite, patch: Accent, terrain: str, rng: random.Random
) -> PlacedObject | None:
    """Stand one dragon dwelling on ``patch`` behind a top-level guard, None when the
    terrain offers none or none fits."""
    pool = dragon_pool(site.catalog, terrain)
    if not pool:
        return None
    footing = PatchFooting(patch.tiles, mine=True)
    first = rng.choice(pool)
    for ident in (first, *smaller(site, pool, first)):
        order = spot_order(patch.tiles, ident)
        obj = site.place(Purpose.DWELLING, ident, order, footing, guard=TOP_TIER)
        if obj is not None:
            return obj
    return None


def place_dragon(
    sites: Mapping[tuple[int, int], ZoneSite], order: Sequence[tuple[int, Accent]], seed: int
) -> tuple[int, Accent] | None:
    """Stand one dragon dwelling on the first patch of ``order`` with room for it, and return
    that patch. None when no patch has room."""
    for level, patch in order:
        site = sites.get((level, patch.place))
        if site is None:
            continue
        terrain = site.catalog.terrain_name(int(patch.terrain))
        if stand_dragon(site, patch, terrain, patch_rng(seed, level, patch)) is not None:
            return level, patch
        x, y = min(patch.tiles)
        print(f"  zone {site.zid}: no dragon dwelling fits the {terrain} patch at {(x, y)}")
    return None


def place_landmarks(
    site: ZoneSite, patches: Sequence[Accent], seed: int, skip: Accent | None = None
) -> int:
    """Stand one landmark on each of the zone's patches at or above the floor but ``skip``,
    the largest first, and return how many stood. A patch with no room logs why."""
    placed = 0
    big = [p for p in patches if p.place == site.zid and p.size >= LANDMARK_FLOOR and p != skip]
    for patch in sorted(big, key=lambda p: (-p.size, min(p.tiles))):
        x, y = min(patch.tiles)
        terrain = site.catalog.terrain_name(int(patch.terrain))
        if place_landmark(site, patch, terrain, patch_rng(seed, site.lf.level, patch)):
            placed += 1
            continue
        print(
            f"  zone {site.zid}: no landmark fits the {terrain} patch at {(x, y)} "
            + f"({patch.size} tiles)"
        )
    return placed
