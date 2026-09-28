"""Seer hut quests: each links a named artifact in one zone to the seer hut that asks
for it in another."""

import random
from collections.abc import Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass

from vcmi_mapgen.core.catalog import Catalog, Trait
from vcmi_mapgen.core.grid.pockets import find_pockets
from vcmi_mapgen.core.model import CoverIndex, Identity, PlacedObject, Tile
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.placement.place import PlaceSpec, PlaceTarget, place_one
from vcmi_mapgen.core.placement.rewards import seerhut_quest
from vcmi_mapgen.core.planning.zone_index import ZoneRecord
from vcmi_mapgen.core.priors.gameplay import GameplayStats

SEERHUT_ZONE_RATIO = 4  # ~1 seer-hut quest per 4 eligible zones -- zone_engine.py's own
# corpus-replay convention for the same object
MAX_SEER_HUTS = 6
SEERHUT_MIN_REACH = 8  # a zone needs at least this many free reachable tiles to be worth
# drawing into a quest (host EITHER the hut or its artifact)


@dataclass(frozen=True, slots=True)
class SeerHutContext:
    gameplay: GameplayStats
    pocket_tiles: AbstractSet[Tile] | None = None
    existing_objs: Sequence[PlacedObject] = ()
    used_artifacts: set[str] | None = None
    cover: CoverIndex | None = None


@dataclass(frozen=True, slots=True)
class _QuestEnv:
    catalog: Catalog
    eligible: Sequence[ZoneRecord]
    ptiles: AbstractSet[Tile]
    used_artifacts: set[str]
    objs: list[PlacedObject]
    bounds: tuple[int, int] | None
    cover: CoverIndex
    gameplay: GameplayStats


def place_seer_hut_quests(
    catalog: Catalog,
    zone_records: Sequence[ZoneRecord],
    context: SeerHutContext,
    seed: int = 1,
    bounds: tuple[int, int] | None = None,
) -> tuple[list[PlacedObject], int]:
    """One or more Seer Hut quests for the WHOLE level (VCMI RMG convention: a seer hut's
    mission gates on a single named artifact the hero must find and hand-carry to it). Each
    quest links two placements in DIFFERENT zones -- the quest's target artifact (an
    unguarded findable pickup, same "always free in open ground" doctrine as scatter loot --
    see the module docstring) and the seer hut itself (a rigid visitable building) -- with the
    hut's `options.quest.limiter.artifacts` naming the exact artifact identity placed for it.

    Runs once per level, after every zone's own gameplay/vegetation/scatter is finalized and
    the map-level G2/island repair has run (so both placements land on truly reachable
    ground), and BEFORE the pocket-cache pass claims the remaining nooks -- `zone_records`'
    `open_set`/`reach` and the cover are shared with that pass, so tiles this function spends are
    already excluded when pockets are judged.

    `context.used_artifacts`, when passed, is a set MUTATED in place and shared across every level's
    call for the same map (see `pp_map.build`) -- a named artifact is a map-unique relic in
    vanilla H3, so one quest's target must never double as another level's target too.

    `zone_records` is a list of {"zid", "terrain", "ts", "open_set", "passable", "reach"}
    (see `pp_map._run_level`/`place_pocket_caches`). Returns (objs, n_quests)."""
    cover = context.cover if context.cover is not None else CoverIndex(context.existing_objs)
    eligible = [zr for zr in zone_records if len(zr.reach - cover.claims) >= SEERHUT_MIN_REACH]
    if len(eligible) < 2:
        return [], 0
    n = min(MAX_SEER_HUTS, max(1, len(eligible) // SEERHUT_ZONE_RATIO))

    rng_pair = random.Random(seed ^ 0xEE47)
    objs: list[PlacedObject] = []
    used_artifacts = context.used_artifacts if context.used_artifacts is not None else set[str]()
    placed = 0
    # Pre-compute which zones have pocket tiles so the per-attempt loop can skip quickly.
    _ptiles_global = _quest_pocket_tiles(zone_records, context.pocket_tiles)
    env = _QuestEnv(
        catalog, eligible, _ptiles_global, used_artifacts, objs, bounds, cover, context.gameplay
    )

    for i in range(n):
        idx_hut, idx_art = rng_pair.sample(range(len(eligible)), 2)
        rng = random.Random(seed ^ (i * 92821) ^ 0xEE47)
        if _place_quest(env, rng, idx_hut, idx_art):
            placed += 1
    return objs, placed


def _quest_pocket_tiles(
    zone_records: Sequence[ZoneRecord], pocket_tiles: AbstractSet[Tile] | None
) -> AbstractSet[Tile]:
    if pocket_tiles is not None:
        return pocket_tiles
    passable_all = set[Tile]().union(*(zr.passable for zr in zone_records))
    raw_p = find_pockets(passable_all)
    _ptiles_acc: set[Tile] = set()
    for _g, (pt, _mf) in raw_p.items():
        if len(pt) >= 3:
            _ptiles_acc |= set(pt)
    return _ptiles_acc


def _place_quest(env: _QuestEnv, rng: random.Random, idx_hut: int, idx_art: int) -> bool:
    eligible = env.eligible
    hut_zr = eligible[idx_hut]

    pool_hut = env.catalog.quest_givers(hut_zr.terrain)
    if not pool_hut:
        return False
    hut_ident = rng.choice(pool_hut)

    # Find an art zone with a ≥3-tile pocket; start with the random pick then
    # try other eligible zones to avoid getting 0 quests when the chosen zone
    # has no pocket tiles available.
    art_zr_order = [eligible[idx_art]] + [
        zr for j, zr in enumerate(eligible) if j not in (idx_art, idx_hut)
    ]
    art_zr, art_ident = _pick_art_zone(env, rng, art_zr_order)
    if art_zr is None or art_ident is None or art_ident.subtype is None:
        return False  # no eligible art zone with a ≥3-tile pocket

    mark = env.cover.mark()
    if _place_art(env, rng, art_zr, art_ident) is None:
        return False

    if not _place_hut(env, rng, hut_zr, hut_ident, art_ident.subtype):
        # no room for the hut => a dangling quest artifact nobody asked for; drop it
        # rather than leave an orphaned reference
        _ = env.objs.pop()
        env.cover.rollback(mark)
        return False

    env.used_artifacts.add(art_ident.subtype)
    return True


def _pick_art_zone(
    env: _QuestEnv, rng: random.Random, art_zr_order: Sequence[ZoneRecord]
) -> tuple[ZoneRecord, Identity] | tuple[None, None]:
    for cand_art_zr in art_zr_order:
        art_eligible = env.ptiles & (cand_art_zr.reach - env.cover.claims)
        if not art_eligible:
            continue
        cand_pool_art = sorted(
            (
                a
                for a in env.catalog.candidates(Purpose.REWARD_PICKUP, cand_art_zr.terrain)
                if a.type in env.catalog.types_with(Trait.ARTIFACT)
                and a.subtype not in env.used_artifacts
            ),
            key=lambda a: a.kind,
        )
        if not cand_pool_art:
            continue
        return cand_art_zr, rng.choice(cand_pool_art)
    return None, None


def _place_art(
    env: _QuestEnv, rng: random.Random, art_zr: ZoneRecord, art_ident: Identity
) -> Tile | None:
    st_art = env.gameplay[art_zr.terrain]
    art_eligible = env.ptiles & (art_zr.reach - env.cover.claims)
    art_cands = sorted(art_eligible)
    rng.shuffle(art_cands)
    target = PlaceTarget(
        env.catalog, env.objs, env.cover, art_zr.reach, rng, st_art, bounds=env.bounds
    )
    spec = PlaceSpec(Purpose.REWARD_PICKUP, None, ident=art_ident)
    for t in art_cands:
        if place_one(target, spec, t[0], t[1]):
            return t
    return None


def _place_hut(
    env: _QuestEnv, rng: random.Random, hut_zr: ZoneRecord, hut_ident: Identity, art_subtype: str
) -> bool:
    st_hut = env.gameplay[hut_zr.terrain]
    hut_cands = sorted(hut_zr.reach - env.cover.claims)
    rng.shuffle(hut_cands)
    quest = seerhut_quest(rng, art_subtype)
    target = PlaceTarget(
        env.catalog, env.objs, env.cover, hut_zr.reach, rng, st_hut, bounds=env.bounds
    )
    spec = PlaceSpec(Purpose.QUEST_GATE, None, ident=hut_ident, payload=quest)
    return any(place_one(target, spec, t[0], t[1]) for t in hut_cands)
