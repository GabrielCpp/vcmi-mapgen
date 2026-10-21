"""The one map-wide pass over the neutral towns, mines, dwellings, banks and visitables. The
map holds each family at the count its group rule gives, split over the bands by the
family's corpus effort, map-wide. No object serves a player: each stands where the players'
reach of its family stays even, under the guard that lifts it into its band. The rare mines
each player needs within reach stand before this pass, and every other rare mine is drawn
like any other family. The neutral towns stand furthest from every other town. Each neutral
town takes its own sawmill and ore pit right after the towns, before any mine. The gold mines
stand last among the mines, on contested land far from every home."""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import PlacedObject
from vcmi_mapgen.core.model.purpose import VISIT_PURPOSES, Purpose
from vcmi_mapgen.core.placement.guard_draw import GuardDraw
from vcmi_mapgen.core.placement.site import ZoneSite
from vcmi_mapgen.core.priors.counts import CountCurve, FamilyCurves
from vcmi_mapgen.core.priors.effort import EffortPriors
from vcmi_mapgen.core.priors.spacing import SpacingPriors
from vcmi_mapgen.core.reading.effort import EffortMap
from vcmi_mapgen.core.reading.families import (
    TOP_LEVEL,
    Families,
    family_purpose,
    guard_levels,
    reach_guard,
)
from vcmi_mapgen.core.reading.mines import MapMeasure
from vcmi_mapgen.core.steps.gameplay.bands import BandPlan, Slot, slot_order, stretched
from vcmi_mapgen.core.steps.gameplay.gold import GoldSpot
from vcmi_mapgen.core.steps.gameplay.pick import Picker
from vcmi_mapgen.core.steps.gameplay.quota import (
    RANKS,
    MapCount,
    family_quota,
    group_rules,
    paired,
    split,
)
from vcmi_mapgen.core.steps.gameplay.reach import Reach
from vcmi_mapgen.core.steps.gameplay.result import Shortfall, SlotRanking
from vcmi_mapgen.core.steps.gameplay.roster import roster
from vcmi_mapgen.core.steps.gameplay.siting import (
    GOLD_FAMILY,
    Siting,
    place_slots,
    standing_visit,
)
from vcmi_mapgen.core.steps.gameplay.spacing import SpotWeight
from vcmi_mapgen.core.steps.gameplay.supply import Supply

VISIT_RANK = 4


@dataclass(frozen=True, slots=True)
class Demand:
    """What the pass asks of the map: its measure, the resource mine and town curves its
    measure reads, the density multiplier on every count, the pairs of enemy players, and
    the corpus fit of each gameplay family, the spacing law of the kinds and the land tiles of
    each level."""

    measure: MapMeasure
    mines: CountCurve
    towns: CountCurve
    density: float = 1.0
    enemies: tuple[tuple[int, int], ...] = ()
    families: FamilyCurves = field(default_factory=FamilyCurves)
    spacing: SpacingPriors = field(default_factory=SpacingPriors)
    land: Mapping[int, int] = field(default_factory=dict[int, int])

    @property
    def players(self) -> int:
        return self.measure.players


@dataclass(frozen=True, slots=True)
class Plan:
    """The slots still to place in placing order, the objects already standing on the
    sites by family, the count of each family each new town's own objects count against,
    dealt once the towns stand, and the player towns."""

    slots: Sequence[Slot]
    standing: Sequence[tuple[str, PlacedObject]]
    paired: Mapping[str, int] = field(default_factory=dict[str, int])
    homes: Sequence[PlacedObject] = ()


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
        groups = group_rules(demand.mines, demand.towns, count, demand.families)
        quota = family_quota(groups, corpus, demand.density, len(homes), self.rng)
        pairs = paired(groups)
        now = {f: n for f, n in sorted(quota.items()) if f not in pairs}
        slots = self._deal(now, standing, maps)
        later = {f: n for f, n in sorted(quota.items()) if f in pairs}
        return Plan(slot_order(slots, RANKS), held, later, list(homes))

    def _deal(
        self,
        quota: Mapping[str, int],
        standing: Mapping[str, Sequence[PlacedObject]],
        maps: Sequence[EffortMap],
    ) -> list[Slot]:
        """The slots of ``quota`` once the objects ``standing`` count against it: the towns
        and the gold mines for no player, every other family band by band, each family's corpus
        effort stretched with the map's land."""
        band_of = self.effort.band
        land = self.demand.measure.land
        corpus = {
            f: stretched(days, self.demand.families.factor(f, land))
            for f, days in self.effort.families.items()
        }
        plan = BandPlan(corpus, band_of, self.demand.players, self.rng)
        slots: list[Slot] = []
        for family, n in quota.items():
            unowned = family == GOLD_FAMILY or family_purpose(family) == Purpose.TOWN
            if unowned and self.demand.players:
                slots += [Slot(family)] * max(0, n - len(standing.get(family, [])))
            else:
                visits = [standing_visit(o, maps) for o in standing.get(family, [])]
                bands = [None if v is None else band_of(v[1]) for v in visits]
                slots += plan.shared(family, n, bands)
        return slots

    def place(
        self,
        plan: Plan,
        picker: Picker,
        price: Callable[[], Sequence[EffortMap]],
        supply: Supply,
    ) -> tuple[Shortfall, tuple[SlotRanking, ...]]:
        """Stand every slot of ``plan`` and tally what stood against what the plan asked,
        with the ranking each slot tried.
        The towns stand first, then ``supply`` stands each new town's own mines. Each of
        those takes one object off the paired families, which are dealt then."""
        reach = Reach(self.demand.players)
        top = min(TOP_LEVEL, len(self.effort.toll) - 1)
        draws = GuardDraw(self.demand.families, top)
        siting = Siting(
            self.sites, picker, self.effort.band, self.rng, reach, self.effort.toll, draws
        )
        siting.homes = plan.homes
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
        picker.see(o for _f, o in stood)
        rest = slot_order([*rest, *self._pairs(plan, len(new), len(stood), price())], RANKS)
        rest, counts = roster(picker, self.sites, rest, self.rng)
        siting.spacing = SpotWeight(self.demand.spacing, counts, self.demand.land)
        shares = self._cap(siting, rest)
        placed += place_slots(siting, rest, rank, price)
        self._report(siting, shares)
        short = Shortfall(Counter(s.family for s in [*towns, *rest]), placed)
        return short, tuple(siting.ranking)

    def _cap(self, siting: Siting, rest: Sequence[Slot]) -> dict[str, int]:
        capped = frozenset([Purpose.MINE, Purpose.DWELLING, Purpose.BANK, *VISIT_PURPOSES])
        siting.capped = capped
        total = sum(family_purpose(s.family) in capped for s in rest) + sum(
            o.purpose in capped for s in self.sites for o in s.objs
        )
        shares = split(total, {str(i): float(len(s.ts)) for i, s in enumerate(self.sites)})
        siting.caps = {
            i: max(0, shares[str(i)] - sum(o.purpose in capped for o in s.objs))
            for i, s in enumerate(self.sites)
        }
        tiles = sum(len(s.ts) for s in self.sites)
        print(f"  zone quota: {total / max(tiles, 1) * 100:.2f} capped objects per 100 tiles")
        return shares

    def _report(self, siting: Siting, shares: Mapping[str, int]) -> None:
        print(f"  zone quota overflow: {siting.overflow}")
        for i, s in enumerate(self.sites):
            stood = sum(o.purpose in siting.capped for o in s.objs)
            print(
                f"  zone quota: level {s.lf.level} zid {s.zid} tiles {len(s.ts)}"
                + f" share {shares[str(i)]} stood {stood}"
            )

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
        return self._deal(quota, standing, maps)

    def _towns(self) -> list[PlacedObject]:
        return [o for s in self.sites for o in s.objs if o.purpose == Purpose.TOWN]
