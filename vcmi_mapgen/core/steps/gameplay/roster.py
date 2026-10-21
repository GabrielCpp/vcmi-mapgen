"""The roster: the kind of every spaced slot, drawn before siting so each kind's count on the
finished map is known."""

from __future__ import annotations

import random
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import replace

from vcmi_mapgen.core.placement.site import ZoneSite
from vcmi_mapgen.core.reading.families import family_purpose
from vcmi_mapgen.core.reading.repeats import SPACED, Kind
from vcmi_mapgen.core.steps.gameplay.bands import Slot
from vcmi_mapgen.core.steps.gameplay.pick import USED_WEIGHT, Picker


def roster(
    picker: Picker, sites: Sequence[ZoneSite], slots: Sequence[Slot], rng: random.Random
) -> tuple[list[Slot], Counter[Kind]]:
    """``slots`` in their order, each spaced slot given a kind, and the count of each kind
    on the finished map: its copies standing plus the slots of the roster that drew it. A
    slot draws its kind by the chance of the kind on each site's terrain, weighed by the
    site's share of the tiles, and a kind that already stands, or was drawn before, weighs
    USED_WEIGHT as much. A slot whose family offers no kind on any site keeps none."""
    total = max(sum(len(s.ts) for s in sites), 1)
    chances: dict[tuple[str, int], dict[Kind, float]] = {}
    drawn: Counter[Kind] = Counter()
    out: list[Slot] = []
    for slot in slots:
        if family_purpose(slot.family) not in SPACED:
            out.append(slot)
            continue
        weights: defaultdict[Kind, float] = defaultdict(float)
        for i, site in enumerate(sites):
            if (slot.family, i) not in chances:
                chances[slot.family, i] = picker.kinds(slot.family, site.zone.terrain, site.st)
            for kind, p in chances[slot.family, i].items():
                weights[kind] += len(site.ts) / total * p
        if not weights:
            out.append(slot)
            continue
        kinds = sorted(weights, key=lambda k: (k[0] or "", k[1] or ""))
        w = [weights[k] * (USED_WEIGHT if picker.stood.get(k) or drawn[k] else 1.0) for k in kinds]
        kind = rng.choices(kinds, weights=w, k=1)[0]
        drawn[kind] += 1
        out.append(replace(slot, kind=kind))
    counts = Counter({k: len(spots) for k, spots in picker.stood.items()})
    counts.update(drawn)
    return out, counts
