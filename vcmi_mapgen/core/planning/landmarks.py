"""The kinds of landmark a spot can hold, their corpus weights and the identities each kind
draws from on one terrain."""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import Identity
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.reading.mines import GOLD

TOP_TIER = 7


@dataclass(frozen=True, slots=True)
class LandmarkKind:
    """One kind of landmark: its name, the purpose it is placed for and its corpus weight."""

    name: str
    purpose: Purpose
    weight: int


GOLD_MINE = LandmarkKind("gold", Purpose.MINE, 83)
ABANDONED_MINE = LandmarkKind("abandoned", Purpose.MINE, 83)
STAT_BUILDING = LandmarkKind("stat", Purpose.STAT_PERMANENT, 132)
DWELLING = LandmarkKind("dwelling", Purpose.DWELLING, 112)
KINDS = (GOLD_MINE, ABANDONED_MINE, STAT_BUILDING, DWELLING)


def kind_order(rng: random.Random, kinds: Sequence[LandmarkKind] = KINDS) -> list[LandmarkKind]:
    """One kind drawn by weight, then the others in list order."""
    first = rng.choices(list(kinds), weights=[k.weight for k in kinds])[0]
    return [first, *(k for k in kinds if k != first)]


def above_top_tier(catalog: Catalog, ident: Identity) -> bool:
    """Whether ``ident`` is a dwelling that recruits above the top guard level."""
    return (catalog.dwelling_level(ident.kind) or 0) > TOP_TIER


def landmark_pool(catalog: Catalog, kind: LandmarkKind, terrain: str) -> list[Identity]:
    """The identities of ``kind`` on ``terrain``, without the dwellings above the top tier
    and the fixed dwellings of a town."""
    if kind == GOLD_MINE:
        return catalog.mines_by_resource(terrain).get(GOLD, [])
    if kind == ABANDONED_MINE:
        return catalog.abandoned_mines(terrain)
    return [
        i
        for i in catalog.candidates(kind.purpose, terrain)
        if not above_top_tier(catalog, i) and catalog.dwelling_faction(i.kind) is None
    ]
