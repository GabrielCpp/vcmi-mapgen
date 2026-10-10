"""The one map-wide pass over the neutral towns, mines, dwellings, banks and visitables. The
map holds each family at the count its group rule gives, the players share each family band
by band, and each object stands where its player reaches it at its target effort. Each
neutral town takes its own sawmill and ore pit right after the towns, before any mine. The
gold mines serve no player and stand last among the mines, on contested land far from every
home."""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import PlacedObject
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.placement.site import MINE_GUARD_LVL, ZoneSite
from vcmi_mapgen.core.priors.counts import CountCurve
from vcmi_mapgen.core.priors.effort import EffortPriors
from vcmi_mapgen.core.reading.effort import EffortMap
from vcmi_mapgen.core.reading.families import (
    Families,
    door_guard,
    family_purpose,
    guard_levels,
    mine_family,
    reach_guard,
)
from vcmi_mapgen.core.reading.mines import RARE_MINE_RES, MapMeasure
from vcmi_mapgen.core.steps.gameplay.bands import BandPlan, Slot, slot_order
from vcmi_mapgen.core.steps.gameplay.gold import GoldSpot
from vcmi_mapgen.core.steps.gameplay.pick import Picker
from vcmi_mapgen.core.steps.gameplay.quota import (
    RANKS,
    MapCount,
    family_quota,
    group_rules,
    paired,
)
from vcmi_mapgen.core.steps.gameplay.reach import Reach
from vcmi_mapgen.core.steps.gameplay.siting import (
    GOLD_FAMILY,
    Siting,
    place_slots,
    standing_cell,
    standing_visit,
)
from vcmi_mapgen.core.steps.gameplay.supply import Supply
from vcmi_mapgen.core.steps.gameplay.turn import Turn, nearest_first, rare_slots

VISIT_RANK = 4
RARE_FAMILIES = frozenset(mine_family(r) for r in RARE_MINE_RES)


@dataclass(frozen=True, slots=True)
class Demand:
    """What the pass asks of the map: its measure, the resource mine and town curves its
    measure reads, the density multiplier on every count, and the pairs of enemy players."""

    measure: MapMeasure
    mines: CountCurve
    towns: CountCurve
    density: float = 1.0
    enemies: tuple[tuple[int, int], ...] = ()

    @property
    def players(self) -> int:
        return self.measure.players


@dataclass(frozen=True, slots=True)
class Plan:
    """The slots still to place in placing order, the objects already standing on the
    sites by family, the count of each family each new town's own objects count against,
    dealt once the towns stand, and the player each family's split starts from."""

    slots: Sequence[Slot]
    standing: Sequence[tuple[str, PlacedObject]]
    paired: Mapping[str, int] = field(default_factory=dict[str, int])
    starts: Mapping[str, int] = field(default_factory=dict[str, int])


@dataclass(frozen=True, slots=True)
class Shortfall:
    """Per family, the objects the plan asked for and the objects that stood."""

    wanted: Mapping[str, int]
    placed: Mapping[str, int]

    def lines(self) -> list[str]:
        return [
            f"{f}: {self.placed.get(f, 0)}/{n}"
            for f, n in sorted(self.wanted.items())
            if self.placed.get(f, 0) < n
        ]


def map_resources(catalog: Catalog, sites: Sequence[ZoneSite]) -> list[str]:
    """The mine resources some site's terrain offers."""
    found = {
        r for s in sites for r, ids in catalog.mines_by_resource(s.zone.terrain).items() if ids
    }
    return sorted(found)


def trim(quota: Mapping[str, int], floor: Mapping[str, int], k: int) -> tuple[dict[str, int], int]:
    """``quota`` less ``k`` objects, each off the family with the most left above its
    ``floor``, the earlier family on a tie, then the count it found no object for."""
    left = dict(quota)
    for taken in range(k):
        open_ = [f for f in left if left[f] > floor.get(f, 0)]
        if not open_:
            return left, k - taken
        family = min(open_, key=lambda f: (floor.get(f, 0) - left[f], f))
        left[family] -= 1
    return left, 0


def rank(purpose: str) -> int:
    """The pricing round of a purpose: one each for towns, mines, dwellings and banks, and
    one for every visitable."""
    return min(RANKS.index(purpose), VISIT_RANK)


@dataclass(frozen=True, slots=True)
class Placement:
    """The one map-wide pass over ``sites``: what to place, then where."""

    catalog: Catalog
    sites: Sequence[ZoneSite]
    effort: EffortPriors
    demand: Demand
    rng: random.Random

    def plan(
        self,
        homes: Collection[PlacedObject],
        sea: Sequence[PlacedObject],
        maps: Sequence[EffortMap],
    ) -> Plan:
        """The slots of every object still to place, in placing order. The objects already
        standing on the sites, the player towns aside, and the ``sea`` objects count against
        their family."""
        catalog, demand = self.catalog, self.demand
        families = Families.of(catalog)
        standing: dict[str, list[PlacedObject]] = {}
        for o in [*(o for s in self.sites for o in s.objs if o not in homes), *sea]:
            f = families.family(catalog, o)
            if f is not None:
                standing.setdefault(f, []).append(o)
        held = [(f, o) for f, objs in sorted(standing.items()) for o in objs]
        grounds = [(len(s.ts), s.st) for s in self.sites]
        corpus = self.effort.families
        count = MapCount(grounds, demand.measure, map_resources(catalog, self.sites), corpus)
        groups = group_rules(demand.mines, demand.towns, count)
        quota = family_quota(groups, corpus, demand.density, len(homes), self.rng)
        pairs = paired(groups)
        starts = {
            f: i % demand.players if demand.players else 0 for i, f in enumerate(sorted(quota))
        }
        now = {f: n for f, n in sorted(quota.items()) if f not in pairs}
        slots = self._deal(now, standing, starts, maps)
        later = {f: n for f, n in sorted(quota.items()) if f in pairs}
        return Plan(slot_order(slots, RANKS), held, later, starts)

    def _deal(
        self,
        quota: Mapping[str, int],
        standing: Mapping[str, Sequence[PlacedObject]],
        starts: Mapping[str, int],
        maps: Sequence[EffortMap],
    ) -> list[Slot]:
        """The slots of ``quota`` once the objects ``standing`` count against it: the rare
        mines dealt in turn along each player's way, the gold mines for no player, every other
        family band by band."""
        band_of = self.effort.band
        plan = BandPlan(self.effort.families, band_of, self.demand.players, self.rng)
        slots: list[Slot] = []
        for family, n in quota.items():
            if family == GOLD_FAMILY and self.demand.players:
                slots += [Slot(family)] * max(0, n - len(standing.get(family, [])))
            elif family not in RARE_FAMILIES:
                cells = [standing_cell(o, maps, band_of) for o in standing.get(family, [])]
                slots += plan.slots(family, n, cells, starts.get(family, 0))
        rare = {f: n for f, n in quota.items() if f in RARE_FAMILIES}
        visits = {f: [standing_visit(o, maps) for o in standing.get(f, [])] for f in rare}
        return slots + rare_slots(plan, rare, visits, starts)

    def place(
        self,
        plan: Plan,
        picker: Picker,
        price: Callable[[], Sequence[EffortMap]],
        supply: Supply,
    ) -> Shortfall:
        """Stand every slot of ``plan`` and tally what stood against what the plan asked.
        The towns stand first, then ``supply`` stands each new town's own mines. Each of
        those takes one object off the paired families, which are dealt then. Each rare mine
        takes its family from the turn where it stands."""
        reach = Reach(self.demand.players)
        siting = Siting(self.sites, picker, self.effort.band, self.rng, reach, self.effort.toll)
        if self.demand.players:
            siting.gold = GoldSpot.of(self.demand.enemies, self.effort.toll)
        guards = guard_levels(self.catalog, (o for s in self.sites for o in s.objs))
        siting.held.extend((f, o, reach_guard(self.catalog, guards, o)) for f, o in plan.standing)
        picker.see(o for _f, o in plan.standing)
        towns = [s for s in plan.slots if family_purpose(s.family) == Purpose.TOWN]
        rest = [s for s in plan.slots if family_purpose(s.family) != Purpose.TOWN]
        before = {id(o) for o in self._towns()}
        placed = place_slots(siting, towns, rank, price)
        new = [o for o in self._towns() if id(o) not in before]
        stood = supply(new)
        siting.held.extend((f, o, 0) for f, o in stood)
        rest = slot_order([*rest, *self._pairs(plan, len(new), len(stood), price())], RANKS)
        rest = nearest_first(rest, RARE_FAMILIES)
        pool = Counter(s.family for s in rest if s.family in RARE_FAMILIES)
        held = [f for f, _o in [*plan.standing, *stood] if f in RARE_FAMILIES]
        offered = {*pool, *held}
        levels = {
            mine_family(r): MINE_GUARD_LVL[r] for r in RARE_MINE_RES if mine_family(r) in offered
        }
        siting.turn = Turn(pool, levels, self.effort.toll, self.demand.players)
        guards = guard_levels(self.catalog, (o for s in self.sites for o in s.objs))
        for f, o in [*plan.standing, *stood]:
            if f in RARE_FAMILIES:
                siting.turn.guards[o.level, o.x, o.y] = door_guard(guards, o)
        placed += place_slots(siting, rest, rank, price)
        return Shortfall(Counter(s.family for s in [*towns, *rest]), placed)

    def _pairs(self, plan: Plan, towns: int, stood: int, maps: Sequence[EffortMap]) -> list[Slot]:
        """The slots of the paired families, less the ``stood`` own mines of the ``towns``
        new towns."""
        standing: dict[str, list[PlacedObject]] = {}
        for f, o in plan.standing:
            standing.setdefault(f, []).append(o)
        floor = {f: len(standing.get(f, [])) for f in plan.paired}
        quota, over = trim(plan.paired, floor, stood)
        if over:
            print(f"  WARNING: the pairs of {towns} towns pass the mine curve by {over}")
        return self._deal(quota, standing, plan.starts, maps)

    def _towns(self) -> list[PlacedObject]:
        return [o for s in self.sites for o in s.objs if o.purpose == Purpose.TOWN]
