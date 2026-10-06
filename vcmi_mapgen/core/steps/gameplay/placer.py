"""The one map-wide pass over the neutral towns, mines, dwellings, banks and visitables. The
map holds each family at the corpus rate per tile, the players share each family band by
band, and each object stands where its player reaches it at its target effort."""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import PlacedObject
from vcmi_mapgen.core.placement.site import ZoneSite
from vcmi_mapgen.core.priors.effort import EffortPriors
from vcmi_mapgen.core.reading.effort import EffortMap
from vcmi_mapgen.core.reading.families import Families, guard_levels, reach_guard
from vcmi_mapgen.core.steps.gameplay.bands import BandPlan, Slot, slot_order
from vcmi_mapgen.core.steps.gameplay.pick import Picker
from vcmi_mapgen.core.steps.gameplay.quota import RANKS, family_quota, purpose_quota
from vcmi_mapgen.core.steps.gameplay.reach import Reach
from vcmi_mapgen.core.steps.gameplay.siting import Siting, place_slots, standing_cell

VISIT_RANK = 4


@dataclass(frozen=True, slots=True)
class Demand:
    """What the pass asks of the map: the players and the density multiplier on the corpus
    rate."""

    players: int
    density: float = 1.0


@dataclass(frozen=True, slots=True)
class Plan:
    """The slots still to place in placing order, and the objects already standing on the
    sites by family."""

    slots: Sequence[Slot]
    standing: Sequence[tuple[str, PlacedObject]]


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
        purposes = purpose_quota(grounds, demand.density, len(homes), self.rng)
        quota = family_quota(purposes, map_resources(catalog, self.sites), self.effort.families)
        band_of = self.effort.band
        plan = BandPlan(self.effort.families, band_of, demand.players, self.rng)
        slots: list[Slot] = []
        for i, (family, n) in enumerate(sorted(quota.items())):
            cells = [standing_cell(o, maps, band_of) for o in standing.get(family, [])]
            start = i % demand.players if demand.players else 0
            slots += plan.slots(family, n, cells, start)
        return Plan(slot_order(slots, RANKS), held)

    def place(
        self, plan: Plan, picker: Picker, price: Callable[[], Sequence[EffortMap]]
    ) -> Shortfall:
        """Stand every slot of ``plan`` and tally what stood against what the plan asked."""
        reach = Reach(self.demand.players)
        siting = Siting(self.sites, picker, self.effort.band, self.rng, reach, self.effort.toll)
        guards = guard_levels(self.catalog, (o for s in self.sites for o in s.objs))
        siting.held.extend((f, o, reach_guard(self.catalog, guards, o)) for f, o in plan.standing)
        placed = place_slots(siting, plan.slots, rank, price)
        return Shortfall(Counter(s.family for s in plan.slots), placed)
