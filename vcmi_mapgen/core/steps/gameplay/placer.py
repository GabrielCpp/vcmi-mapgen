"""The one map-wide pass over the neutral towns, mines, dwellings, banks and visitables. The
map holds each family at the count its group rule gives, the players share each family band
by band, and each object stands where its player reaches it at its target effort. Each
neutral town takes its own sawmill and ore pit right after the towns, before any mine."""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import PlacedObject
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.placement.site import ZoneSite
from vcmi_mapgen.core.priors.effort import EffortPriors
from vcmi_mapgen.core.priors.mines import MineCurve
from vcmi_mapgen.core.reading.effort import EffortMap
from vcmi_mapgen.core.reading.families import (
    Families,
    family_purpose,
    guard_levels,
    reach_guard,
)
from vcmi_mapgen.core.reading.mines import MapMeasure
from vcmi_mapgen.core.steps.gameplay.bands import BandPlan, Slot, slot_order
from vcmi_mapgen.core.steps.gameplay.pick import Picker
from vcmi_mapgen.core.steps.gameplay.quota import (
    RANKS,
    MapCount,
    family_quota,
    group_rules,
    paired,
)
from vcmi_mapgen.core.steps.gameplay.reach import Reach
from vcmi_mapgen.core.steps.gameplay.siting import Siting, place_slots, standing_cell
from vcmi_mapgen.core.steps.gameplay.supply import Supply

VISIT_RANK = 4


@dataclass(frozen=True, slots=True)
class Demand:
    """What the pass asks of the map: its measure, the resource mine curve its measure reads,
    and the density multiplier on every count."""

    measure: MapMeasure
    curve: MineCurve
    density: float = 1.0

    @property
    def players(self) -> int:
        return self.measure.players


@dataclass(frozen=True, slots=True)
class Plan:
    """The slots still to place in placing order, the objects already standing on the
    sites by family, and the families each new town's own objects count against."""

    slots: Sequence[Slot]
    standing: Sequence[tuple[str, PlacedObject]]
    paired: frozenset[str] = frozenset()


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


def trim(slots: Sequence[Slot], families: Collection[str], k: int) -> tuple[list[Slot], int]:
    """``slots`` less ``k`` slots of ``families``, each the last slot of the family with
    the most slots left, then the count it found no slot for."""
    left = list(slots)
    for taken in range(k):
        counts = Counter(s.family for s in left if s.family in families)
        if not counts:
            return left, k - taken
        family = min(counts, key=lambda f: (-counts[f], f))
        del left[max(i for i, s in enumerate(left) if s.family == family)]
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
        groups = group_rules(demand.curve, count)
        quota = family_quota(groups, corpus, demand.density, len(homes), self.rng)
        band_of = self.effort.band
        plan = BandPlan(self.effort.families, band_of, demand.players, self.rng)
        slots: list[Slot] = []
        for i, (family, n) in enumerate(sorted(quota.items())):
            cells = [standing_cell(o, maps, band_of) for o in standing.get(family, [])]
            start = i % demand.players if demand.players else 0
            slots += plan.slots(family, n, cells, start)
        return Plan(slot_order(slots, RANKS), held, paired(groups))

    def place(
        self,
        plan: Plan,
        picker: Picker,
        price: Callable[[], Sequence[EffortMap]],
        supply: Supply,
    ) -> Shortfall:
        """Stand every slot of ``plan`` and tally what stood against what the plan asked.
        The towns stand first, then ``supply`` stands each new town's own mines, and each
        of those takes one slot off the paired families."""
        reach = Reach(self.demand.players)
        siting = Siting(self.sites, picker, self.effort.band, self.rng, reach, self.effort.toll)
        guards = guard_levels(self.catalog, (o for s in self.sites for o in s.objs))
        siting.held.extend((f, o, reach_guard(self.catalog, guards, o)) for f, o in plan.standing)
        towns = [s for s in plan.slots if family_purpose(s.family) == Purpose.TOWN]
        rest = [s for s in plan.slots if family_purpose(s.family) != Purpose.TOWN]
        before = {id(o) for o in self._towns()}
        placed = place_slots(siting, towns, rank, price)
        new = [o for o in self._towns() if id(o) not in before]
        stood = supply(new)
        siting.held.extend((f, o, 0) for f, o in stood)
        rest, over = trim(rest, plan.paired, len(stood))
        if over:
            print(f"  WARNING: the pairs of {len(new)} towns pass the mine curve by {over}")
        placed += place_slots(siting, rest, rank, price)
        return Shortfall(Counter(s.family for s in [*towns, *rest]), placed)

    def _towns(self) -> list[PlacedObject]:
        return [o for s in self.sites for o in s.objs if o.purpose == Purpose.TOWN]
