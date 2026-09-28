"""Water-body population and seaport guarantee — Gameplay-timing logic (runs before
vegetation forbids their footprint), despite `place_water`'s old home in pp_pickup.py.

Also owns `pick_identity`/`legal_cells`, the low-level identity-pick/footprint-legality helpers
`place_water` needs: Gameplay is the first step in pipeline order to need them, so
`steps/placement.py` (for the scatter, gated, treasure and loot placers, which need the
exact same helpers) imports them from here rather than duplicating them.
"""

import collections
import random
import zlib
from collections.abc import Callable, Container, Iterable, Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from typing import final

from vcmi_mapgen import ontology as ON
from vcmi_mapgen.kit import objects as OR
from vcmi_mapgen.kit.terrain_lookup import TNAME
from vcmi_mapgen.models import CoverIndex, Identity, PlacedObject, Role, Tile, Zone, footprint
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

_WATER, _ROCK = 8, 9
_NB4 = ((1, 0), (-1, 0), (0, 1), (0, -1))


def pick_identity(
    pool: Iterable[Identity],
    purpose: str,
    st_t: TerrainStats,
    rng: random.Random,
    art_share: float = 0.45,
) -> Identity | None:
    """Identity for a pickup. The H3 convention (user-mandated): favour the editor's RANDOM
    classes — random resource, tiered random artifacts — over fixed ones. `art_share` is
    the random-artifact probability for REWARD_PICKUP: high for guarded caches, low for
    unguarded scatter (which draws the fixed LOOT pool — treasure chests, campfires —
    weighted by the corpus mix, where the chest dominates)."""
    if purpose == "RESOURCE_PILE" and rng.random() < 0.6:
        return ON.identity_of(RND_RES)
    if purpose == "REWARD_PICKUP" and rng.random() < art_share:
        anim = rng.choices([a for a, _w, _v in RND_ART], weights=[w for _a, w, _v in RND_ART], k=1)[
            0
        ]
        return ON.identity_of(anim)
    return _pick_fixed_identity(pool, purpose, st_t, rng)


def _pick_fixed_identity(
    pool: Iterable[Identity], purpose: str, st_t: TerrainStats, rng: random.Random
) -> Identity | None:
    pool = sorted(
        (i for i in pool if "random" not in (i.type or "").lower()),
        key=lambda i: i.animation,
    )
    if not pool:
        return None
    w = st_t.anim_w.get(purpose, {})
    return rng.choices(pool, weights=[w.get(i.animation.lower(), 0) + 0.2 for i in pool], k=1)[0]


@dataclass(frozen=True, slots=True)
class CellRules:
    bounds: tuple[int, int] | None = None
    interactive_only: bool = False


DEFAULT_CELL_RULES = CellRules()


def legal_cells(
    ident: Identity,
    anchor: Tile,
    open_set: Container[Tile],
    used: Container[Tile],
    rules: CellRules = DEFAULT_CELL_RULES,
) -> list[Tile] | None:
    """A pickup/guard placement is legal if its INTERACTIVE cell(s) sit on an unused,
    placement-eligible tile.  V-overlay cells (sprite bleed) may overlap terrain/walls.

    interactive_only=True: only the interactive (A/X) cell is checked against `used` and
    bounds, and only that cell is returned for claiming.  Use this for dense fill passes
    where adjacent pickups' V-cells would otherwise falsely block each other — V cells are
    cosmetic in H3/VCMI and two objects sharing V-cell space is legal."""
    x, y = anchor
    cells = [(tx, ty) for tx, ty, _b in OR.mask_cells(ident.mask, x, y)]
    interactive = OR.mask_interactive_cells(ident.mask, x, y) or cells
    check = interactive if rules.interactive_only else cells
    if rules.bounds is not None:
        bw, bh = rules.bounds
        if any(not (0 <= tx < bw and 0 <= ty < bh) for tx, ty in check):
            return None
    if any(c in used for c in check):
        return None
    if all(c in open_set and c not in used for c in interactive):
        return check
    return None


def _water_obj(
    ident: Identity,
    t: Tile,
    purpose: str,
    field: tuple[AbstractSet[Tile], set[Tile]],
    cover: CoverIndex,
) -> tuple[PlacedObject, list[Tile]] | None:
    ts, used = field
    cells = legal_cells(ident, t, ts, used)
    if cells is None:
        return None
    solid = tuple(row.replace("V", " ") for row in ident.mask)
    if any((tx, ty) not in ts for tx, ty, _b in OR.mask_cells(solid, t[0], t[1])):
        return None
    obj = PlacedObject.at(ident, t, purpose=purpose)
    if not cover.try_add(obj):
        return None
    return obj, cells


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
    cover = CoverIndex()
    for p in WATER_PURPOSES:
        x = st.counts.get(p, 0) / st.tiles * area
        n = min(int(x) + (1 if rng.random() < x - int(x) else 0), 14)
        if not n:
            continue
        pool = ON.pool(p, "water")
        cands = sorted(ts)
        placed: list[Tile] = []
        for t in rng.choices(cands, k=50 * n):
            if len(placed) >= n:
                break
            if any(max(abs(t[0] - q[0]), abs(t[1] - q[1])) < 4 for q in placed):
                continue
            ident = _pick_fixed_identity(pool, p, st, rng)
            if ident is None:
                break
            placed_obj = _water_obj(ident, t, p, (ts, used), cover)
            if placed_obj is None:
                continue
            obj, cells = placed_obj
            used.update(cells)
            objs.append(obj)
            placed.append(t)
    return objs


@dataclass(frozen=True, slots=True)
class SeaMap:
    W: int
    H: int
    grid: Sequence[Sequence[int]]
    zones: Mapping[int, Zone]
    reserved: AbstractSet[Tile] = frozenset()
    accept: Callable[[PlacedObject], bool] | None = None
    score: Callable[[Identity, Tile], int] | None = None
    placed: Callable[[PlacedObject], None] | None = None
    quiet: bool = False


def ensure_water_seaports(
    sea: SeaMap,
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
    water_tiles = {(x, y) for y in range(sea.H) for x in range(sea.W) if sea.grid[y][x] == _WATER}
    if not water_tiles:
        return []
    return _SeaportPlanner(sea, water_tiles, objs, seed, ontology).run()


def _land_zone_of(zones: Mapping[int, Zone]) -> dict[Tile, int]:
    land_zone_of: dict[Tile, int] = {}
    for zid, z in zones.items():
        if TNAME.get(z.terrain_type) in (None, "water", "rock"):
            continue
        for t in z.tiles_set:
            land_zone_of[t] = zid
    return land_zone_of


def _existing_blocking(objs: Iterable[PlacedObject]) -> set[Tile]:
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
    return existing_blk


def _structure_fronts(objs: Iterable[PlacedObject]) -> tuple[set[Tile], list[set[Tile]]]:
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
    return structure_blk, structure_fronts


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


def _expand_inland(near_coastal: set[Tile], ts_set: AbstractSet[Tile]) -> set[Tile]:
    for _ in range(SEAPORT_SEARCH_HOPS):
        for t in list(near_coastal):
            for dx, dy in _NB4:
                nb = (t[0] + dx, t[1] + dy)
                if nb in ts_set:
                    near_coastal.add(nb)
    return near_coastal


def _water_component(t0: Tile, water_tiles: AbstractSet[Tile]) -> set[Tile]:
    comp, q = {t0}, [t0]
    while q:
        x, y = q.pop()
        for dx, dy in _NB4:
            n = (x + dx, y + dy)
            if n in water_tiles and n not in comp:
                comp.add(n)
                q.append(n)
    return comp


@final
class _SeaportPlanner:
    def __init__(
        self,
        sea: SeaMap,
        water_tiles: set[Tile],
        objs: list[PlacedObject],
        seed: int,
        ontology: Ontology,
    ) -> None:
        self.sea = sea
        self.water_tiles = water_tiles
        self.objs = objs
        self.seed = seed
        self.ontology = ontology

        # land tile → zone id
        self.land_zone_of = _land_zone_of(sea.zones)

        # All blocking/interactive cells of existing objects
        self.existing_blk = _existing_blocking(objs)

        # Every already-placed non-guard structure's own front row (s8 diagnosis, 2026-09:
        # a seaport landed squarely in an arena's front row, sealing it off -- nothing
        # checked a new placement against an existing structure's own approach). Guards
        # are exempt on both sides: their ZoC may still block a front tile, and they have
        # no "front" of their own worth protecting.
        self.structure_blk, self.structure_fronts = _structure_fronts(objs)

        self.interactive_tiles: set[Tile] = set()
        self.covered_tiles: set[Tile] = set()
        for o in objs:
            self._register(o)

        self.new_objs: list[PlacedObject] = []
        # Anchor positions of seaports already in objs (for 20-tile spacing constraint)
        self.placed_anchors = [(o.x, o.y) for o in objs if o.type == "shipyard"]

    def _warn(self, msg: str) -> None:
        if not self.sea.quiet:
            print(msg)

    def _register(self, o: PlacedObject) -> None:
        for tile, role in footprint(o):
            self.covered_tiles.add(tile)
            if role in (Role.VISIT, Role.ENTRANCE, Role.APPROACH):
                self.interactive_tiles.add(tile)

    def _stacks_on_others(self, ident: Identity, ax: int, ay: int) -> bool:
        probe = PlacedObject.at(ident, (ax, ay), purpose="WATER_TRANSPORT")
        for tile, role in footprint(probe):
            if role is Role.APPROACH:
                if tile in self.covered_tiles:
                    return True
            elif tile in self.interactive_tiles or (
                role in (Role.ENTRANCE, Role.VISIT) and tile in self.covered_tiles
            ):
                return True
        return False

    def _blocks_a_structure_front(self, cand_blk: AbstractSet[Tile]) -> bool:
        return any(front <= (self.structure_blk | cand_blk) for front in self.structure_fronts)

    def _candidate_ok(
        self, ts_set: AbstractSet[Tile], ident: Identity, ax: int, ay: int, check_spacing: bool
    ) -> bool:
        allc, blk, approach = _seaport_footprint(ax, ay, ident.mask)
        if any(c not in ts_set for c in allc):
            return False
        if approach not in ts_set:
            return False
        # Approach tile must not be occupied (dark-green X tile must be accessible)
        if approach in self.existing_blk:
            return False
        if any(c in self.existing_blk for c in blk):
            return False
        if any(c in self.sea.reserved for c in allc):
            return False
        # At least one BXB cell must be 4-adjacent to water
        if not any((bx + dx, by + dy) in self.water_tiles for bx, by in blk for dx, dy in _NB4):
            return False
        if self._blocks_a_structure_front(set(blk)) or self._stacks_on_others(ident, ax, ay):
            return False
        if check_spacing and any(
            (ax - px) ** 2 + (ay - py) ** 2 < SEAPORT_SPACING_SQ for px, py in self.placed_anchors
        ):
            return False
        accept = self.sea.accept
        return accept is None or accept(PlacedObject.at(ident, (ax, ay), purpose="WATER_TRANSPORT"))

    def _do_place(self, ident: Identity, ax: int, ay: int) -> PlacedObject:
        _, blk, _ = _seaport_footprint(ax, ay, ident.mask)
        self.existing_blk.update(blk)
        self.structure_blk.update(blk)
        front = OR.front_tiles(ident.mask, ax, ay)
        if front:
            self.structure_fronts.append(front)
        self.placed_anchors.append((ax, ay))
        o = PlacedObject.at(ident, (ax, ay), purpose="WATER_TRANSPORT")
        self.new_objs.append(o)
        self._register(o)
        if self.sea.placed is not None:
            self.sea.placed(o)
        return o

    def _try_place(
        self,
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
        rng = random.Random(self.seed ^ zlib.crc32(label.encode()) ^ 0x53A9)
        shuffled = list(cand_tiles)
        rng.shuffle(shuffled)
        cap = shuffled
        score = self.sea.score
        if score is not None:
            cap.sort(key=lambda t: -score(ident, t))

        for ax, ay in cap:
            if self._candidate_ok(ts_set, ident, ax, ay, check_spacing=True):
                return self._do_place(ident, ax, ay)
        if force:
            for ax, ay in cap:
                if self._candidate_ok(ts_set, ident, ax, ay, check_spacing=False):
                    return self._do_place(ident, ax, ay)
        return None

    def _has_seaport(self, ts_set: AbstractSet[Tile]) -> bool:
        """True if any existing or new seaport's dock row is in `ts_set`."""
        for o in self.objs + self.new_objs:
            if o.type != "shipyard":
                continue
            # seaport BXB row at y=o["y"]: cells o["x"]-2..o["x"]
            ax, ay = o.x, o.y
            if any((ax - 2 + i, ay) in ts_set for i in range(3)):
                return True
        return False

    def _zone_has_seaport(self, _zid: int, ts_set: AbstractSet[Tile]) -> bool:
        return self._has_seaport(ts_set)

    def _shore_clusters(self, comp: AbstractSet[Tile]) -> list[set[Tile]]:
        """Maximal 8-connected clusters of land tiles bordering water component `comp`
        -- the physical shores a seaport actually serves, spanning zone boundaries."""
        shore: set[Tile] = set()
        for wx, wy in comp:
            for dx, dy in _NB4:
                t = (wx + dx, wy + dy)
                if t in self.land_zone_of:
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

    def _shipyard_ident(self, terrain: str) -> Identity | None:
        return next(
            (i for i in self.ontology.pool("WATER_TRANSPORT", terrain) if i.type == "shipyard"),
            None,
        )

    def _shore_shipyard(self, zids_here: Iterable[int]) -> Identity | None:
        ident: Identity | None = None
        for zid in zids_here:
            terrain = TNAME.get(self.sea.zones[zid].terrain_type)
            if terrain is None:
                continue
            ident = self._shipyard_ident(terrain)
            if ident is not None:
                break
        return ident

    def _place_for_shore(self, shore: AbstractSet[Tile], label: str) -> bool:
        """Ensure this shore (spanning however many zones) has a seaport; candidates are
        drawn from the near-coastal expansion of the WHOLE shore, and `ts_set` is the
        union of every zone the shore touches -- not one zone's own tiles alone."""
        if self._has_seaport(shore):
            return True
        zids_here = sorted({self.land_zone_of[t] for t in shore})
        ts_set: set[Tile] = set()
        for zid in zids_here:
            ts_set |= set(self.sea.zones[zid].tiles_set)
        ident = self._shore_shipyard(zids_here)
        if ident is None:
            self._warn(
                f"  WARNING: no seaport placed on shore near zone(s) {zids_here} "
                + f"({len(shore)} shore tiles) — no shipyard identity for any "
                + "bordering terrain"
            )
            return False
        # Expand inland (across the whole shore, any of its zones) so the footprint
        # can anchor deep enough for its blocking row to still reach the water edge.
        near_coastal = _expand_inland(set(shore), ts_set)
        o = self._try_place(ts_set, list(near_coastal), label, ident)
        if not o:
            self._warn(
                f"  WARNING: no seaport placed on shore near zone(s) {zids_here} "
                + f"({len(shore)} shore tiles) — no valid near-coastal anchor found"
            )
            return False
        return True

    def _coastal_set(self, ts_set: AbstractSet[Tile]) -> set[Tile]:
        W, H, grid = self.sea.W, self.sea.H, self.sea.grid
        return {
            t
            for t in ts_set
            if any(
                0 <= t[0] + dx < W and 0 <= t[1] + dy < H and grid[t[1] + dy][t[0] + dx] == _WATER
                for dx, dy in _NB4
            )
        }

    def _place_for_zone(self, zid: int, z: Zone, label: str) -> bool:
        """Ensure zone zid has a seaport; restrict to near-coastal tiles only."""
        ts_set = set(z.tiles_set)
        if self._zone_has_seaport(zid, ts_set):
            return True
        terrain = TNAME.get(z.terrain_type)
        if terrain is None:
            return False
        ident = self._shipyard_ident(terrain)
        if ident is None:
            self._warn(
                f"  WARNING: no seaport placed on zone {zid} "
                + f"({terrain}, {z.area} tiles) — no shipyard identity for this terrain"
            )
            return False
        # Coastal = zone tiles adjacent to water
        coastal_set = self._coastal_set(ts_set)
        if not coastal_set:
            return False
        # Expand inland so the footprint can anchor deep enough for its blocking row
        # to still reach the water edge.
        near_coastal = _expand_inland(set(coastal_set), ts_set)
        o = self._try_place(ts_set, list(near_coastal), label, ident)
        if not o:
            self._warn(
                f"  WARNING: no seaport placed on zone {zid} "
                + f"({terrain}, {z.area} tiles) — "
                + "no valid near-coastal anchor found"
            )
            return False
        return True

    def _serve_shores(self, comp: AbstractSet[Tile], t0: Tile) -> None:
        zones = self.sea.zones
        for i, shore in enumerate(self._shore_clusters(comp)):
            # Skip only if EVERY zone touching this shore is a tiny sliver -- the gate
            # is about not bothering with a sliver zone's own economy, not the shore
            # ring's own tile count (which can be modest even for a huge zone).
            zids_here = {self.land_zone_of[t] for t in shore}
            if max(zones[zid].area for zid in zids_here) < BORDER_ZONE_MIN_AREA:
                continue
            _ = self._place_for_shore(shore, f"wb_{t0}_{i}")

    def _is_island(self, ts_set: AbstractSet[Tile]) -> bool:
        W, H, grid = self.sea.W, self.sea.H, self.sea.grid
        return all(
            grid[ny][nx] in (_WATER, _ROCK)
            for x, y in ts_set
            for dx, dy in _NB4
            for nx, ny in [(x + dx, y + dy)]
            if 0 <= nx < W and 0 <= ny < H and (nx, ny) not in ts_set
        )

    def run(self) -> list[PlacedObject]:
        # ── 1. Water-body guarantee: one seaport per SHORE (not per land zone) ────
        seen_w: set[Tile] = set()
        for t0 in sorted(self.water_tiles):
            if t0 in seen_w:
                continue
            comp = _water_component(t0, self.water_tiles)
            seen_w |= comp
            if len(comp) < SEA_ZONE_MIN_AREA:
                continue

            self._serve_shores(comp, t0)

        # ── 2. Island guarantee ───────────────────────────────────────────────────
        for zid, z in sorted(self.sea.zones.items()):
            terrain = TNAME.get(z.terrain_type)
            if terrain in (None, "water", "rock") or z.area < ISLAND_MIN_AREA:
                continue
            ts_set = set(z.tiles_set)
            is_island = self._is_island(ts_set)
            if not is_island:
                continue
            _ = self._place_for_zone(zid, z, f"island_{zid}")

        return self.new_objs
