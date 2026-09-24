"""Subterranean Gate placement — Gate-only logic split out of pp_gameplay.py.

Also owns the low-level gameplay-footprint fitting helpers (`footprint_cells`/`fits`/`GAP`) and
`rnd_monster`: GateStep is the first step in pipeline order to need them, and Gameplay/
Pickup/Repair (which need the same helpers for mines, pocket guards, and portal rescue)
import them from here rather than duplicating them or inventing a generic shared module.
"""

import json
import random
from collections.abc import Container, Iterable
from collections.abc import Set as AbstractSet
from dataclasses import dataclass

from vcmi_mapgen import ontology as ON
from vcmi_mapgen.kit import json_value as jv
from vcmi_mapgen.kit import objects as OR
from vcmi_mapgen.kit.paths import project_root
from vcmi_mapgen.models import Identity, PlacedObject, Tile

ROOT = project_root()
GATE_STATS_PATH = ROOT / "data" / "pp" / "gate_stats.json"
GATE_STATS_VERSION = 1
NO_TILES: frozenset[Tile] = frozenset()
MIN_AREA_STATS = 60

GATE_ANIM = "avtcave"  # SUBTERRANEAN_GATE — single un-suffixed sprite variant

RND_MON = tuple(f"avwmon{i}" for i in range(1, 8))  # randomMonsterLevel 1..7

GAP = 2  # free tiles kept between any two gameplay footprints — gameplay
# neighbours VEGETATION (which fills the gap), not other gameplay


@dataclass(frozen=True, slots=True)
class GateStats:
    per_1000_tiles: float
    n_maps: int


type Fit = tuple[list[Tile], list[Tile], Tile]
type LevelGates = tuple[list[PlacedObject], set[Tile], set[Tile], list[Tile]]


def rnd_monster(lvl: int) -> Identity:
    """Random-monster identity of a level, clamped to 1..7."""
    return ON.identity_of(RND_MON[max(1, min(7, int(lvl))) - 1])


def footprint_cells(
    ident: Identity, ax: int, ay: int
) -> tuple[list[Tile], list[Tile], Tile | None]:
    """(all_cells, blocking_cells, approach) of an identity anchored at (ax, ay); approach is
    the tile a hero stands on to visit ('X' = enter from below; 'A' = the tile itself)."""
    allc: list[Tile] = []
    blk: list[Tile] = []
    approach: Tile | None = None
    rows = ident.mask
    hh = len(rows)
    for r, row in enumerate(rows):
        ww = len(row)
        for ci, ch in enumerate(row):
            if ch == " ":
                continue
            tx, ty = ax - (ww - 1 - ci), ay - (hh - 1 - r)
            allc.append((tx, ty))
            if ch in ("B", "X"):
                blk.append((tx, ty))
            if ch == "X":
                approach = (tx, ty + 1)
            elif ch == "A" and approach is None:
                approach = (tx, ty)
    return allc, blk, approach


def fits(
    ident: Identity,
    ax: int,
    ay: int,
    ts: Container[Tile],
    occupied: Container[Tile],
    near: Container[Tile],
    reserved: Container[Tile],
    avoid: Container[Tile] = NO_TILES,
) -> Fit | None:
    """Legality: whole footprint in-zone, at least GAP free tiles from every other gameplay
    footprint (`near` = existing cells inflated by GAP), no squatting on an earlier object's
    approach tile (`reserved`), own approach tile in-zone and standable. `avoid` (the
    underground tunnel/gate-connector protect set — empty on the surface) keeps gameplay
    footprints off cells terrain generation already fought to keep walkable: those cells
    are guarded from vegetation via `protected_web`, but gameplay placement runs BEFORE
    that web is built, so without this check a town/mine/monster footprint could still
    silently wall off a corridor that vegetation would otherwise have left alone."""
    allc, blk, approach = footprint_cells(ident, ax, ay)
    if approach is None:
        return None
    for cell in allc:
        if cell not in ts or cell in near or cell in reserved or cell in avoid:
            return None
    if approach not in ts or approach in occupied or approach in blk or approach in avoid:
        return None
    return allc, blk, approach


def mine_gate_stats(force: bool = False) -> GateStats:
    """Corpus SUBTERRANEAN_GATE frequency: gates per 1000 underground (non-rock) tiles,
    averaged over two-level corpus maps — scales generated gate counts to map size, the same
    density-driven approach as every other placed purpose (never a hand-picked constant)."""
    if not force and GATE_STATS_PATH.exists():
        st = jv.as_object(jv.loads(GATE_STATS_PATH.read_text()))
        if st.get("_version") == GATE_STATS_VERSION:
            rate = st.get("per_1000_tiles")
            return GateStats(
                per_1000_tiles=float(rate) if isinstance(rate, int | float) else 0.0,
                n_maps=jv.as_int(st.get("n_maps")),
            )
    rates: list[float] = []
    for nm in OR.all_map_names():
        try:
            fm = OR.load_faithful(nm)
        except Exception:
            continue
        if len(fm.terrain) < 2:
            continue
        ug = fm.terrain[1]
        ug_area = sum(1 for row in ug for c in row if c.t != 9)
        if ug_area < MIN_AREA_STATS:
            continue
        n_gates = sum(
            1
            for o in fm.objects
            if o.level == 0 and (o.animation or "").lower().removesuffix(".def") == "avtcave"
        )
        rates.append(n_gates / ug_area * 1000)
    per_1000 = sum(rates) / len(rates) if rates else 3.0
    GATE_STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _ = GATE_STATS_PATH.write_text(
        json.dumps(
            {"_version": GATE_STATS_VERSION, "per_1000_tiles": per_1000, "n_maps": len(rates)}
        )
    )
    return GateStats(per_1000_tiles=per_1000, n_maps=len(rates))


def place_gates(
    ts0: AbstractSet[Tile],
    ts1: AbstractSet[Tile],
    occ0: Iterable[Tile],
    occ1: Iterable[Tile],
    appr0: Iterable[Tile] = NO_TILES,
    appr1: Iterable[Tile] = NO_TILES,
    seed: int = 1,
) -> tuple[LevelGates, LevelGates]:
    """Subterranean Gate pairs: one `avtcave` object at the IDENTICAL (x, y) on both levels —
    `kit/reachability.py`'s `_gate_links` already pairs gates by exact-(x, y) match, so no other
    linking is needed. Candidates are tiles walkable on BOTH levels (`ts0 & ts1`); footprint
    legality (`fits`, reused unchanged) is checked against the UNION of both levels' already-
    placed gameplay footprints (`occ0`/`occ1`, GAP-inflated the same way `place_zone` does
    internally) plus their existing approach tiles (`appr0`/`appr1`, so a gate can never
    squat on a mine's or town's doorway), so a gate can never land on top of existing
    objects on either side. Gate count is corpus-scaled (`mine_gate_stats`), clamped to a
    sane range for typical map sizes. The underground-side approach — the harder, descending
    direction — gets a random monster guard at the corpus zone-gate probability (0.65,
    matching `place_zone`'s own gate-band convention); the surface side is left open.

    Returns `(objs0, occ0, blk0, appr0), (objs1, occ1, blk1, appr1)` — the same 4-tuple shape
    `place_zone` returns per level, so `pp_map.build()` folds gate placement into its existing
    per-level object/occupied/blocked/approach aggregation with no special-casing."""
    rng = random.Random(seed ^ 0x6A7E)
    objs0: list[PlacedObject] = []
    objs1: list[PlacedObject] = []
    occ0n: set[Tile] = set()
    occ1n: set[Tile] = set()
    blk0n: set[Tile] = set()
    blk1n: set[Tile] = set()
    appr0n: list[Tile] = []
    appr1n: list[Tile] = []
    ts_both = ts0 & ts1
    if not ts_both:
        return (objs0, occ0n, blk0n, appr0n), (objs1, occ1n, blk1n, appr1n)
    st = mine_gate_stats()
    target = max(2, min(6, round(st.per_1000_tiles * len(ts1) / 1000)))
    ident = ON.identity_of(GATE_ANIM)
    cands = sorted(ts_both)
    rng.shuffle(cands)
    occupied = set(occ0) | set(occ1)
    near: set[Tile] = set()
    for cx, cy in occupied:
        for gx in range(-GAP, GAP + 1):
            for gy in range(-GAP, GAP + 1):
                near.add((cx + gx, cy + gy))
    reserved = set(appr0) | set(appr1)
    for c in cands:
        if len(objs0) >= target:
            break
        fit = fits(ident, c[0], c[1], ts_both, occupied, near, reserved)
        if fit is None:
            continue
        allc, blk, approach = fit
        occupied.update(allc)
        for cx, cy in allc:
            for gx in range(-GAP, GAP + 1):
                for gy in range(-GAP, GAP + 1):
                    near.add((cx + gx, cy + gy))
        reserved.add(approach)
        for lvl, objs, occn, blkn, apprn in (
            (0, objs0, occ0n, blk0n, appr0n),
            (1, objs1, occ1n, blk1n, appr1n),
        ):
            objs.append(PlacedObject.at(ident, c[0], c[1], level=lvl, purpose="TRANSPORT"))
            occn.update(allc)
            blkn.update(blk)
            apprn.append(approach)
        if rng.random() < 0.65:  # guard only the underground (descending) approach
            gident = rnd_monster(3)
            objs1.append(
                PlacedObject.at(
                    gident,
                    approach[0],
                    approach[1],
                    level=1,
                    purpose="GUARD",
                    options={"character": "hostile"},
                )
            )
            occ1n.add(approach)
    return (objs0, occ0n, blk0n, appr0n), (objs1, occ1n, blk1n, appr1n)
