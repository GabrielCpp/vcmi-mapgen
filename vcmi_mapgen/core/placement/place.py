"""``place_one``, the shared placement primitive, and the reachability BFS it places against."""

import collections
import random
from collections.abc import Collection, Container, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import (
    CoverIndex,
    Identity,
    JsonValue,
    PlacedObject,
    Tile,
)
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.placement import footprint as FP
from vcmi_mapgen.core.placement.cells import CellRules, legal_cells
from vcmi_mapgen.core.placement.identity import pick_fixed_identity, pick_random_identity
from vcmi_mapgen.core.placement.rewards import pandora_reward
from vcmi_mapgen.core.priors.gameplay import TerrainStats


def web_dist(open_set: AbstractSet[Tile], prot: Collection[Tile]) -> dict[Tile, int]:
    """4-connected BFS steps from the protected web through the open field. Tiles absent
    from the result are UNREACHABLE (sealed by vegetation) — nothing may be placed there."""
    d = {t: 0 for t in prot if t in open_set}
    q = collections.deque(d)
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (x + dx, y + dy)
            if n in open_set and n not in d:
                d[n] = d[(x, y)] + 1
                q.append(n)
    return d


def scatter_reach(open_set: AbstractSet[Tile], prot: Collection[Tile]) -> set[Tile]:
    return set(web_dist(open_set, prot))


@dataclass(frozen=True, slots=True)
class PlaceTarget:
    catalog: Catalog
    objs: list[PlacedObject]
    cover: CoverIndex
    reach: AbstractSet[Tile]
    rng: random.Random
    st: TerrainStats
    bounds: tuple[int, int] | None = None


@dataclass(frozen=True, slots=True)
class PlaceSpec:
    purpose: str
    pool: Sequence[Identity] | None = None
    ident: Identity | None = None
    art_share: float = 0.45
    cache: bool = False
    options: dict[str, JsonValue] | None = None
    interactive_only: bool = False
    clear_of: Container[Tile] | None = None


def _guard_cells(
    target: PlaceTarget, spec: PlaceSpec, ident: Identity, x: int, y: int
) -> list[Tile] | None:
    # a guard's mask carries decorative overlay cells (H3's monster sprites always
    # bleed into surrounding scenery) alongside its one interactive cell -- at a
    # genuine chokepoint the surroundings are mostly blocked/unreachable BY
    # DEFINITION, so requiring the whole footprint free (like legal_cells does) means the
    # guard can almost never actually land on the neck. Only the interactive cell has
    # to be free & reachable; the rest may fall outside `reach`, overlap terrain, or
    # overlap another object's cells -- V cells are pure non-blocking sprite extent,
    # and the pocket the guard seals is BY DESIGN packed with caches up/left of the
    # mouth. Rejecting on claimed overlap silently dropped the guard from 31 of 39
    # earned pockets on a real 72x72 build (every nook north/west of its mouth),
    # leaving the treasure free -- the exact opposite of the cache grammar.
    interactive = FP.interactive_cells(ident.footprint, x, y)
    if not interactive or not all(
        c in target.reach and c not in target.cover.claims for c in interactive
    ):
        return None
    if spec.clear_of is not None and not FP.overlay_clear(ident.footprint, x, y, spec.clear_of):
        return None
    if spec.interactive_only:
        return interactive
    cells = [(tx, ty) for tx, ty, _b in FP.anchored_cells(ident.footprint, x, y)]
    if target.bounds is not None:
        bw, bh = target.bounds
        cells = [(tx, ty) for tx, ty in cells if 0 <= tx < bw and 0 <= ty < bh]
    return cells


def _apply_options(o: PlacedObject, ident: Identity, spec: PlaceSpec, rng: random.Random) -> None:
    if spec.purpose == Purpose.GUARD:  # absent => VCMI 'compliant' => every creature joins free
        o.options = {"character": "hostile"}
    if spec.options is not None:
        o.options = spec.options
    elif ident.type == "pandoraBox":  # absent => legal but permanently empty reward
        o.options = pandora_reward(rng)
    elif ident.type == "spellScroll":
        # VCMI's spellScroll object has exactly one registered subtype ("object") --
        # the spell itself is carried in options.spell, never in subtype (confirmed
        # against lib/mapping/MapFormatJson.cpp's CGArtifact deserialization). ident's
        # own "subtype" is where the spell name was stashed by the caller's identity
        # pool, so move it across before overwriting it.
        o.options = {"spell": ident.subtype}
        o.subtype = "object"


def place_one(target: PlaceTarget, spec: PlaceSpec, x: int, y: int) -> bool:
    """Shared placement primitive for both scatter and pocket caches: resolve an identity,
    check its footprint against `reach` and the cover's claims, and if legal append the obj
    and claim its cells. Returns whether it landed.

    interactive_only: passed to legal_cells — only the A-cell is checked/claimed so adjacent
    pickups' V-cells never block each other (use for dense fill passes)."""
    rng = target.rng
    ident = (
        spec.ident
        or pick_random_identity(target.catalog, spec.purpose, rng, spec.art_share)
        or pick_fixed_identity(spec.pool or (), spec.purpose, target.st, rng)
    )
    if ident is None:
        return False
    if spec.purpose == Purpose.GUARD:
        cells = _guard_cells(target, spec, ident, x, y)
    else:
        cells = legal_cells(
            ident,
            (x, y),
            target.reach,
            target.cover.claims,
            CellRules(bounds=target.bounds, interactive_only=spec.interactive_only),
        )
    if cells is None:
        return False
    o = PlacedObject.at(ident, (x, y), purpose=spec.purpose)
    if not target.cover.try_claim(o, cells):
        return False
    _apply_options(o, ident, spec, rng)
    if spec.cache:  # a guarded-pocket pickup, not open scatter — informational marker only,
        o.cache = True  # ignored by the vmap exporter, used by tests
    target.objs.append(o)
    return True
