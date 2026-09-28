"""Placement primitives shared by every step that places objects over the open field:
the reachability BFS, a guard's zone of control, the guard spacing rule, ``place_one``
and the pandoraBox reward helpers."""

import collections
import random
from collections.abc import Collection, Container, Iterable, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass

from vcmi_mapgen.core.model import CoverIndex, Identity, JsonValue, PlacedObject, Tile
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.model.resource import Resource
from vcmi_mapgen.core.steps.gameplay import mines as PG
from vcmi_mapgen.core.steps.gameplay.water import CellRules, legal_cells, pick_identity
from vcmi_mapgen.kit import objects as OR

GUARD_SPACING = 2

PANDORA_CREATURES = (
    "pikeman",
    "centaur",
    "gremlin",
    "imp",
    "skeleton",
    "troglodyte",
    "goblin",
    "gnoll",
    "peasant",
)  # vanilla tier-1 dwelling
# creatures, one per RoE town plus the neutral peasant -- a modest
# unguarded-scatter payload, not cache-treasure tier.

RW_TEXT: dict[str, JsonValue] = {
    "exactStrings": None,
    "localStrings": None,
    "message": None,
    "numbers": None,
    "stringsTextID": None,
}
RW_LIMITER: dict[str, JsonValue] = {
    "allOf": [],
    "anyOf": [],
    "artifacts": [],
    "creatures": [],
    "dayOfWeek": 0,
    "daysPassed": 0,
    "heroExperience": 0,
    "heroLevel": -1,
    "manaPercentage": 0,
    "manaPoints": 0,
    "movePercentage": 0,
    "movePoints": 0,
    "noneOf": [],
    "primary": [0, 0, 0, 0],
    "secondary": [],
}
RW_REWARD: dict[str, JsonValue] = {
    "creatures": [],
    "creaturesChange": [],
    "heroExperience": 0,
    "heroLevel": 0,
    "manaDiff": 0,
    "manaOverflowFactor": 0,
    "manaPercentage": -1,
    "moveOverflowFactor": 0,
    "movePercentage": -1,
    "movePoints": 0,
    "primary": [0, 0, 0, 0],
    "resources": {},
    "secondary": [],
    "spellCast": {"level": 0},
}


def _pandora_reward(rng: random.Random) -> dict[str, JsonValue]:
    """A VCMI 'Rewardable' payload for a pandoraBox (schema captured verbatim from a real
    VCMI-RMG .vmap: `options.rewardable.info[].reward` alongside a sibling all-null
    `guardMessage`). Without this an unconfigured pandoraBox is legal but permanently
    empty -- every field defaults to 0/-1/null, which is a no-op reward. Kept modest
    (gold/experience/a small creature stack): this fires from the unguarded-scatter loot
    pool, not a guarded cache."""
    reward = dict(RW_REWARD)
    flavor = rng.choices(("gold", "experience", "creatures"), weights=(45, 30, 25), k=1)[0]
    if flavor == "gold":
        reward["resources"] = {Resource.GOLD: rng.choice((500, 1000, 1500, 2000, 3000, 5000))}
    elif flavor == "experience":
        reward["heroExperience"] = rng.choice((1000, 1500, 2500, 5000, 7500, 10000))
    else:
        reward["creatures"] = [
            {"type": f"core:{rng.choice(PANDORA_CREATURES)}", "amount": rng.randint(3, 10)}
        ]
    return {
        "guardMessage": dict(RW_TEXT),
        "rewardable": {
            "info": [
                {
                    "limiter": dict(RW_LIMITER),
                    "message": dict(RW_TEXT),
                    "reward": reward,
                    "visitType": 1,
                }
            ],
            "infoWindowType": 0,
            "onSelect": dict(RW_TEXT),
            "resetParameters": {"period": 0},
            "selectMode": "selectFirst",
            "visitMode": "unlimited",
        },
    }


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


def guard_zoc(objs: Sequence[PlacedObject]) -> set[Tile]:
    """Every tile inside some guard's zone of control: the interactive cell plus its 8
    neighbours. A hero stepping on one of them fights the guard."""
    zoc: set[Tile] = set()
    for o in objs:
        if o.purpose != Purpose.GUARD or not o.mask:
            continue
        for ix, iy in OR.mask_interactive_cells(o.mask, o.x, o.y):
            zoc.add((ix, iy))
            zoc.update((ix + dx, iy + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1))
    return zoc


def guard_spaced(t: Tile, guards: Iterable[Tile]) -> bool:
    """True when no guard in ``guards`` stands within Chebyshev ``GUARD_SPACING`` of ``t``.
    Every step that places a guard refuses a tile this rejects, so no two guards crowd one
    crossing."""
    return all(max(abs(t[0] - g[0]), abs(t[1] - g[1])) > GUARD_SPACING for g in guards)


def scatter_reach(open_set: AbstractSet[Tile], prot: Collection[Tile]) -> set[Tile]:
    return set(web_dist(open_set, prot))


@dataclass(frozen=True, slots=True)
class PlaceTarget:
    objs: list[PlacedObject]
    used: set[Tile]
    reach: AbstractSet[Tile]
    rng: random.Random
    st: PG.TerrainStats
    bounds: tuple[int, int] | None = None
    cover: CoverIndex | None = None


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
    # mouth. Rejecting on `used` overlap silently dropped the guard from 31 of 39
    # earned pockets on a real 72x72 build (every nook north/west of its mouth),
    # leaving the treasure free -- the exact opposite of the cache grammar.
    interactive = OR.mask_interactive_cells(ident.mask, x, y)
    if not interactive or not all(c in target.reach and c not in target.used for c in interactive):
        return None
    if spec.clear_of is not None and not OR.overlay_clear(ident.mask, x, y, spec.clear_of):
        return None
    if spec.interactive_only:
        return interactive
    cells = [(tx, ty) for tx, ty, _b in OR.mask_cells(ident.mask, x, y)]
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
        o.options = _pandora_reward(rng)
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
    check its footprint against `reach`/`used`, and if legal append the obj and claim its
    cells. Returns whether it landed.

    interactive_only: passed to legal_cells — only the A-cell is checked/claimed so adjacent
    pickups' V-cells never block each other (use for dense fill passes)."""
    rng = target.rng
    ident = spec.ident or pick_identity(
        spec.pool or (), spec.purpose, target.st, rng, art_share=spec.art_share
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
            target.used,
            CellRules(bounds=target.bounds, interactive_only=spec.interactive_only),
        )
    if cells is None:
        return False
    o = PlacedObject.at(ident, (x, y), purpose=spec.purpose)
    if target.cover is not None and not target.cover.try_add(o):
        return False
    target.used.update(cells)
    _apply_options(o, ident, spec, rng)
    if spec.cache:  # a guarded-pocket pickup, not open scatter — informational marker only,
        o.cache = True  # ignored by the vmap exporter, used by tests
    target.objs.append(o)
    return True
