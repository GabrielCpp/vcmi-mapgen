"""Water-body population and seaport guarantee — Gameplay-timing logic (runs before
vegetation forbids their footprint), despite `place_water`'s old home in pp_pickup.py.

Also owns `pick_identity`/`legal_cells`, the low-level identity-pick/footprint-legality helpers
`place_water` needs: Gameplay is the first step in pipeline order to need them, so
`steps/pickup/scatter.py` (added in a later phase, for place_scatter/place_pockets/etc.,
which need the exact same helpers) imports them from here rather than duplicating them.
"""

import collections
import random
import zlib
from collections.abc import Container, Iterable, Mapping, Sequence
from collections.abc import Set as AbstractSet

from vcmi_mapgen import ontology as ON
from vcmi_mapgen.kit import objects as OR
from vcmi_mapgen.kit.terrain_lookup import TNAME
from vcmi_mapgen.models import Identity, PlacedObject, Tile, Zone
from vcmi_mapgen.ontology import Ontology
from vcmi_mapgen.steps.gameplay.mines import (
    RND_ART,
    RND_RES,
    WATER_PURPOSES,
    TerrainStats,
    mine_gameplay,
)

SEA_ZONE_MIN_AREA = 50  # minimum water-body size to require a seaport per shore
ISLAND_MIN_AREA = 50  # minimum island-zone size to require a seaport
BORDER_ZONE_MIN_AREA = 30  # skip a seaport on a bordering land zone too small to bother
SEAPORT_SPACING_SQ = 30 * 30  # minimum squared Euclidean distance between seaports
SEAPORT_SEARCH_HOPS = 2  # near-coastal search depth (s10 diagnosis, 2026-09: the
# shipyard mask ['VVV','VVV','BXB'] can need its anchor up to
# 2 tiles inland of the water-adjacent blocking cell -- a
# single hop sometimes misses every valid anchor on an
# otherwise perfectly placeable shore, even after grouping by
# shore instead of by land zone


def pick_identity(
    pool: Iterable[Identity],
    purpose: str,
    st_t: TerrainStats,
    rng: random.Random,
    allow_random: bool = True,
    art_share: float = 0.45,
) -> Identity | None:
    """Identity for a pickup. The H3 convention (user-mandated): favour the editor's RANDOM
    classes — random resource, tiered random artifacts — over fixed ones. `art_share` is
    the random-artifact probability for REWARD_PICKUP: high for guarded caches, low for
    unguarded scatter (which draws the fixed LOOT pool — treasure chests, campfires —
    weighted by the corpus mix, where the chest dominates)."""
    if allow_random and purpose == "RESOURCE_PILE" and rng.random() < 0.6:
        return ON.identity_of(RND_RES)
    if allow_random and purpose == "REWARD_PICKUP" and rng.random() < art_share:
        anim = rng.choices([a for a, _w, _v in RND_ART], weights=[w for _a, w, _v in RND_ART], k=1)[
            0
        ]
        return ON.identity_of(anim)
    pool = sorted(
        (i for i in pool if "random" not in (i.type or "").lower()),
        key=lambda i: i.animation,
    )
    if not pool:
        return None
    w = st_t.anim_w.get(purpose, {})
    return rng.choices(pool, weights=[w.get(i.animation.lower(), 0) + 0.2 for i in pool], k=1)[0]


def legal_cells(
    ident: Identity,
    x: int,
    y: int,
    open_set: Container[Tile],
    used: Container[Tile],
    bounds: tuple[int, int] | None = None,
    interactive_only: bool = False,
) -> list[Tile] | None:
    """A pickup/guard placement is legal if its INTERACTIVE cell(s) sit on an unused,
    placement-eligible tile.  V-overlay cells (sprite bleed) may overlap terrain/walls.

    interactive_only=True: only the interactive (A/X) cell is checked against `used` and
    bounds, and only that cell is returned for claiming.  Use this for dense fill passes
    where adjacent pickups' V-cells would otherwise falsely block each other — V cells are
    cosmetic in H3/VCMI and two objects sharing V-cell space is legal."""
    cells = [(tx, ty) for tx, ty, _b in OR.mask_cells(ident.mask, x, y)]
    interactive = OR.mask_interactive_cells(ident.mask, x, y) or cells
    check = interactive if interactive_only else cells
    if bounds is not None:
        bw, bh = bounds
        if any(not (0 <= tx < bw and 0 <= ty < bh) for tx, ty in check):
            return None
    if any(c in used for c in check):
        return None
    if all(c in open_set and c not in used for c in interactive):
        return check
    return None


def place_water(
    ts: AbstractSet[Tile], _zones: Mapping[int, Zone], zid: int, seed: int = 1
) -> list[PlacedObject]:
    """Populate a WATER zone (spec point: water must not be empty): flotsam/sea chests
    (pickups), buoys/mermaids/sirens (bonus), boats + whirlpools (navigability), shipwrecks/
    derelicts (banks), ocean bottles. No monster: a GUARD only ever gates a mine, a
    loot-zone/portal-rescue access object, or a pocket mouth (user-mandated placement
    order) -- water bodies get none. Densities and animation mix come from the corpus
    water pass; identities from the ontology's water pools."""
    st = mine_gameplay().get("water")
    if not st or not st.tiles:
        return []
    rng = random.Random(seed ^ (zid * 55313) ^ 0x5EA)
    area = len(ts)
    objs: list[PlacedObject] = []
    used: set[Tile] = set()
    for p in WATER_PURPOSES:
        x = st.counts.get(p, 0) / st.tiles * area
        n = min(int(x) + (1 if rng.random() < x - int(x) else 0), 14)
        if not n:
            continue
        pool = ON.gameplay_pool("water", p)
        cands = sorted(ts)
        placed: list[Tile] = []
        for t in rng.choices(cands, k=50 * n):
            if len(placed) >= n:
                break
            if any(max(abs(t[0] - q[0]), abs(t[1] - q[1])) < 4 for q in placed):
                continue
            ident = pick_identity(pool, p, st, rng, allow_random=False)
            if ident is None:
                break
            cells = legal_cells(ident, t[0], t[1], ts, used)
            if cells is None:
                continue
            used.update(cells)
            objs.append(PlacedObject.at(ident, t[0], t[1], purpose=p))
            placed.append(t)
    return objs


def ensure_water_seaports(
    W: int,
    H: int,
    grid: Sequence[Sequence[int]],
    zones: Mapping[int, Zone],
    objs: list[PlacedObject],
    seed: int,
    ontology: Ontology,
) -> list[PlacedObject]:
    """Guarantee ≥1 shipyard per SHORE bordering a water body ≥ SEA_ZONE_MIN_AREA tiles,
    and ≥1 shipyard per island land zone ≥ ISLAND_MIN_AREA tiles.

    A 'shore' is a maximal 8-connected cluster of land tiles bordering one water body --
    NOT a land zone (s10 diagnosis, 2026-09: "analyze the shores depending on the sea
    zones, don't take into account the number of land zones associated with shores"). A
    single water body's coastline can be split into several disconnected shores (separate
    islands/peninsulas around the same sea); grouping by land zone instead used to leave
    an ENTIRE shore unseaported whenever every zone touching it individually was too
    small/jagged to fit a shipyard's footprint alone -- even though the shore as a whole,
    spanning several zones, clearly has room somewhere along it (confirmed empirically: of
    a real 72x72 map's main sea, one shore -- spanning six land zones -- got zero
    seaports while every zone on it failed placement on its own, while the other, smaller,
    single-zone shore succeeded trivially). Placement candidates are now drawn from the
    WHOLE shore's near-coastal expansion (every zone it touches), not one zone's own tiles.

    Placement uses any anchor in the zone where the shipyard's footprint fits with all its
    cells and the approach tile in the zone, and no blocking-cell conflict with existing
    objects. The shipyard identity (type/subtype/animation/mask) comes from `ontology` --
    resolved per target zone's terrain, like every other placed object in this file --
    not a hardcoded animation/mask (the ontology's shipyard entry happens to be identical
    across all land terrains, but sourcing it this way is what keeps it that way on
    purpose rather than by accident).

    Returns list of new shipyard objects to append to `objs`."""
    WATER, ROCK = 8, 9
    NB4 = ((1, 0), (-1, 0), (0, 1), (0, -1))

    water_tiles = {(x, y) for y in range(H) for x in range(W) if grid[y][x] == WATER}
    if not water_tiles:
        return []

    # land tile → zone id
    land_zone_of: dict[Tile, int] = {}
    for zid, z in zones.items():
        if TNAME.get(z.terrain_type) in (None, "water", "rock"):
            continue
        for t in z.tiles_set:
            land_zone_of[t] = zid

    # All blocking/interactive cells of existing objects
    existing_blk: set[Tile] = set()
    for o in objs:
        mask_rows = o.mask
        ax, ay = o.x, o.y
        hh = len(mask_rows)
        for r, row in enumerate(mask_rows):
            ww = len(row)
            for ci, ch in enumerate(row):
                if ch in ("B", "X", "A"):
                    tx = ax - (ww - 1 - ci)
                    ty = ay - (hh - 1 - r)
                    existing_blk.add((tx, ty))

    # Every already-placed non-guard structure's own front row (s8 diagnosis, 2026-09:
    # a seaport landed squarely in an arena's front row, sealing it off -- nothing
    # checked a new placement against an existing structure's own approach). Guards
    # are exempt on both sides: their ZoC may still block a front tile, and they have
    # no "front" of their own worth protecting.
    structure_blk: set[Tile] = set()
    structure_fronts: list[set[Tile]] = []
    for o in objs:
        if o.purpose == "GUARD":
            continue
        mask_rows = o.mask
        if not mask_rows:
            continue
        for cx, cy, blk in OR.mask_cells(mask_rows, o.x, o.y):
            if blk:
                structure_blk.add((cx, cy))
        front = OR.front_tiles(mask_rows, o.x, o.y)
        if front:
            structure_fronts.append(front)

    def _blocks_a_structure_front(cand_blk: AbstractSet[Tile]) -> bool:
        return any(front <= (structure_blk | cand_blk) for front in structure_fronts)

    new_objs: list[PlacedObject] = []
    # Anchor positions of seaports already in objs (for 20-tile spacing constraint)
    placed_anchors = [(o.x, o.y) for o in objs if o.type == "shipyard"]

    def _seaport_footprint(
        ax: int, ay: int, mask: Sequence[str]
    ) -> tuple[list[Tile], list[Tile], Tile | None]:
        allc: list[Tile] = []
        blk: list[Tile] = []
        approach: Tile | None = None
        hh = len(mask)
        for r, row in enumerate(mask):
            ww = len(row)
            for ci, ch in enumerate(row):
                tx = ax - (ww - 1 - ci)
                ty = ay - (hh - 1 - r)
                allc.append((tx, ty))
                if ch in ("B", "X"):
                    blk.append((tx, ty))
                if ch == "X":
                    approach = (tx, ty + 1)
        return allc, blk, approach

    def _try_place(
        ts_set: AbstractSet[Tile],
        cand_tiles: Iterable[Tile],
        label: str,
        ident: Identity,
        force: bool = True,
    ) -> PlacedObject | None:
        """Try to place a shipyard with the given ontology identity. cand_tiles =
        anchor candidates (coastal tiles first). Prefers positions ≥20 tiles from
        existing seaports; when force=True (required placement) falls back to any
        valid position if no spaced candidate exists."""
        # NOTE: Python's built-in hash() is salted per-process for str (PYTHONHASHSEED),
        # so seeding from hash(label) would make this non-reproducible across runs even
        # for the identical seed — crc32 is a plain, stable string->int hash.
        rng = random.Random(seed ^ zlib.crc32(label.encode()) ^ 0x53A9)
        shuffled = list(cand_tiles)
        rng.shuffle(shuffled)
        cap = shuffled[:300]

        def _candidate_ok(ax: int, ay: int, check_spacing: bool) -> bool:
            allc, blk, approach = _seaport_footprint(ax, ay, ident.mask)
            if any(c not in ts_set for c in allc):
                return False
            if approach not in ts_set:
                return False
            # Approach tile must not be occupied (dark-green X tile must be accessible)
            if approach in existing_blk:
                return False
            if any(c in existing_blk for c in blk):
                return False
            # At least one BXB cell must be 4-adjacent to water
            if not any((bx + dx, by + dy) in water_tiles for bx, by in blk for dx, dy in NB4):
                return False
            if _blocks_a_structure_front(set(blk)):
                return False
            return not (
                check_spacing
                and any(
                    (ax - px) ** 2 + (ay - py) ** 2 < SEAPORT_SPACING_SQ
                    for px, py in placed_anchors
                )
            )

        def _do_place(ax: int, ay: int) -> PlacedObject:
            _, blk, _ = _seaport_footprint(ax, ay, ident.mask)
            existing_blk.update(blk)
            structure_blk.update(blk)
            front = OR.front_tiles(ident.mask, ax, ay)
            if front:
                structure_fronts.append(front)
            placed_anchors.append((ax, ay))
            o = PlacedObject.at(ident, ax, ay, purpose="WATER_TRANSPORT")
            new_objs.append(o)
            return o

        for ax, ay in cap:
            if _candidate_ok(ax, ay, check_spacing=True):
                return _do_place(ax, ay)
        if force:
            for ax, ay in cap:
                if _candidate_ok(ax, ay, check_spacing=False):
                    return _do_place(ax, ay)
        return None

    def _has_seaport(ts_set: AbstractSet[Tile]) -> bool:
        """True if any existing or new seaport's dock row is in `ts_set`."""
        for o in objs + new_objs:
            if o.type != "shipyard":
                continue
            # seaport BXB row at y=o["y"]: cells o["x"]-2..o["x"]
            ax, ay = o.x, o.y
            if any((ax - 2 + i, ay) in ts_set for i in range(3)):
                return True
        return False

    def _zone_has_seaport(_zid: int, ts_set: AbstractSet[Tile]) -> bool:
        return _has_seaport(ts_set)

    def _shore_clusters(comp: AbstractSet[Tile]) -> list[set[Tile]]:
        """Maximal 8-connected clusters of land tiles bordering water component `comp`
        -- the physical shores a seaport actually serves, spanning zone boundaries."""
        shore: set[Tile] = set()
        for wx, wy in comp:
            for dx, dy in NB4:
                t = (wx + dx, wy + dy)
                if t in land_zone_of:
                    shore.add(t)
        DIRS8 = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1))
        seen: set[Tile] = set()
        clusters: list[set[Tile]] = []
        for s in sorted(shore):
            if s in seen:
                continue
            cl: set[Tile] = set()
            q = collections.deque([s])
            seen.add(s)
            cl.add(s)
            while q:
                cx, cy = q.popleft()
                for dx, dy in DIRS8:
                    nb = (cx + dx, cy + dy)
                    if nb in shore and nb not in seen:
                        seen.add(nb)
                        cl.add(nb)
                        q.append(nb)
            clusters.append(cl)
        return clusters

    def _place_for_shore(shore: AbstractSet[Tile], label: str) -> bool:
        """Ensure this shore (spanning however many zones) has a seaport; candidates are
        drawn from the near-coastal expansion of the WHOLE shore, and `ts_set` is the
        union of every zone the shore touches -- not one zone's own tiles alone."""
        if _has_seaport(shore):
            return True
        zids_here = sorted({land_zone_of[t] for t in shore})
        ts_set: set[Tile] = set()
        for zid in zids_here:
            ts_set |= set(zones[zid].tiles_set)
        ident: Identity | None = None
        for zid in zids_here:
            terrain = TNAME.get(zones[zid].terrain_type)
            if terrain is None:
                continue
            ident = next(
                (
                    i
                    for i in ontology.gameplay_pool(terrain, "WATER_TRANSPORT")
                    if i.type == "shipyard"
                ),
                None,
            )
            if ident is not None:
                break
        if ident is None:
            print(
                f"  WARNING: no seaport placed on shore near zone(s) {zids_here} "
                + f"({len(shore)} shore tiles) — no shipyard identity for any "
                + "bordering terrain"
            )
            return False
        # Expand inland (across the whole shore, any of its zones) so the footprint
        # can anchor deep enough for its blocking row to still reach the water edge.
        near_coastal = set(shore)
        for _ in range(SEAPORT_SEARCH_HOPS):
            for t in list(near_coastal):
                for dx, dy in NB4:
                    nb = (t[0] + dx, t[1] + dy)
                    if nb in ts_set:
                        near_coastal.add(nb)
        o = _try_place(ts_set, list(near_coastal), label, ident)
        if not o:
            print(
                f"  WARNING: no seaport placed on shore near zone(s) {zids_here} "
                + f"({len(shore)} shore tiles) — no valid near-coastal anchor found"
            )
            return False
        return True

    def _place_for_zone(zid: int, z: Zone, label: str) -> bool:
        """Ensure zone zid has a seaport; restrict to near-coastal tiles only."""
        ts_set = set(z.tiles_set)
        if _zone_has_seaport(zid, ts_set):
            return True
        terrain = TNAME.get(z.terrain_type)
        if terrain is None:
            return False
        ident = next(
            (i for i in ontology.gameplay_pool(terrain, "WATER_TRANSPORT") if i.type == "shipyard"),
            None,
        )
        if ident is None:
            print(
                f"  WARNING: no seaport placed on zone {zid} "
                + f"({terrain}, {z.area} tiles) — no shipyard identity for this terrain"
            )
            return False
        # Coastal = zone tiles adjacent to water
        coastal_set = {
            t
            for t in ts_set
            if any(
                0 <= t[0] + dx < W and 0 <= t[1] + dy < H and grid[t[1] + dy][t[0] + dx] == WATER
                for dx, dy in NB4
            )
        }
        if not coastal_set:
            return False
        # Expand inland so the footprint can anchor deep enough for its blocking row
        # to still reach the water edge.
        near_coastal = set(coastal_set)
        for _ in range(SEAPORT_SEARCH_HOPS):
            for t in list(near_coastal):
                for dx, dy in NB4:
                    nb = (t[0] + dx, t[1] + dy)
                    if nb in ts_set:
                        near_coastal.add(nb)
        o = _try_place(ts_set, list(near_coastal), label, ident)
        if not o:
            print(
                f"  WARNING: no seaport placed on zone {zid} "
                + f"({terrain}, {z.area} tiles) — "
                + "no valid near-coastal anchor found"
            )
            return False
        return True

    # ── 1. Water-body guarantee: one seaport per SHORE (not per land zone) ────
    seen_w: set[Tile] = set()
    for t0 in sorted(water_tiles):
        if t0 in seen_w:
            continue
        comp, q = {t0}, [t0]
        while q:
            x, y = q.pop()
            for dx, dy in NB4:
                n = (x + dx, y + dy)
                if n in water_tiles and n not in comp:
                    comp.add(n)
                    q.append(n)
        seen_w |= comp
        if len(comp) < SEA_ZONE_MIN_AREA:
            continue

        for i, shore in enumerate(_shore_clusters(comp)):
            # Skip only if EVERY zone touching this shore is a tiny sliver -- the gate
            # is about not bothering with a sliver zone's own economy, not the shore
            # ring's own tile count (which can be modest even for a huge zone).
            zids_here = {land_zone_of[t] for t in shore}
            if max(zones[zid].area for zid in zids_here) < BORDER_ZONE_MIN_AREA:
                continue
            _ = _place_for_shore(shore, f"wb_{t0}_{i}")

    # ── 2. Island guarantee ───────────────────────────────────────────────────
    for zid, z in sorted(zones.items()):
        terrain = TNAME.get(z.terrain_type)
        if terrain in (None, "water", "rock") or z.area < ISLAND_MIN_AREA:
            continue
        ts_set = set(z.tiles_set)
        is_island = all(
            grid[ny][nx] in (WATER, ROCK)
            for x, y in ts_set
            for dx, dy in NB4
            for nx, ny in [(x + dx, y + dy)]
            if 0 <= nx < W and 0 <= ny < H and (nx, ny) not in ts_set
        )
        if not is_island:
            continue
        _ = _place_for_zone(zid, z, f"island_{zid}")

    return new_objs
