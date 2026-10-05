"""Standing the dealt sets and the fallback prizes on their held slots."""

from __future__ import annotations

import random
from collections.abc import Mapping
from dataclasses import dataclass

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import CoverIndex, Identity, PlacedObject
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.placement.place import PlaceSpec, PlaceTarget, place_one
from vcmi_mapgen.core.placement.prizes import HeldPrize
from vcmi_mapgen.core.priors.gameplay import GameplayStats
from vcmi_mapgen.core.steps.sets.deal import Deal


@dataclass(frozen=True, slots=True)
class Board:
    """Each level's cover with the held slots free again, the level-0 gameplay statistics and
    the map bounds."""

    covers: Mapping[int, CoverIndex]
    gameplay: GameplayStats
    bounds: tuple[int, int]


def _place(
    catalog: Catalog, board: Board, held: HeldPrize, spec: PlaceSpec, rng: random.Random
) -> PlacedObject | None:
    placed: list[PlacedObject] = []
    target = PlaceTarget(
        catalog,
        placed,
        board.covers[held.level],
        frozenset({held.tile}),
        rng,
        board.gameplay[held.terrain],
        board.bounds,
    )
    if not place_one(target, spec, *held.tile):
        return None
    [o] = placed
    o.level = held.level
    return o


def _pickup(ident: Identity) -> PlaceSpec:
    return PlaceSpec(Purpose.REWARD_PICKUP, ident=ident, cache=True, interactive_only=True)


def stand_deal(
    catalog: Catalog, board: Board, deal: Deal, rng: random.Random
) -> list[PlacedObject] | None:
    """Every part of the set on its slot, or none of them when one part fails."""
    marks = {lvl: c.mark() for lvl, c in board.covers.items()}
    objs: list[PlacedObject] = []
    for slot, part in deal.parts:
        ident = catalog.artifact(part)
        o = _place(catalog, board, slot.held, _pickup(ident), rng) if ident else None
        if o is None:
            for lvl, c in board.covers.items():
                c.rollback(marks[lvl])
            return None
        objs.append(o)
    return objs


def stand_fallback(
    catalog: Catalog, board: Board, held: HeldPrize, rng: random.Random
) -> PlacedObject | None:
    """The slot's own basket artifact, else a resource pile of its terrain."""
    piles = catalog.candidates(Purpose.RESOURCE_PILE, held.terrain)
    specs = [_pickup(held.fallback)]
    if piles:
        specs.append(
            PlaceSpec(
                Purpose.RESOURCE_PILE,
                piles,
                ident=rng.choice(piles),
                cache=True,
                interactive_only=True,
            )
        )
    for spec in specs:
        if (o := _place(catalog, board, held, spec, rng)) is not None:
            return o
    return None


@dataclass(frozen=True, slots=True)
class Stood:
    """The deals that stood, each with its parts, and the fallback prize of every slot no set
    took, or None when the slot stayed empty."""

    sets: list[tuple[Deal, list[PlacedObject]]]
    fallbacks: list[PlacedObject | None]

    def objs(self) -> list[PlacedObject]:
        return [
            *(o for _, parts in self.sets for o in parts),
            *(o for o in self.fallbacks if o is not None),
        ]


def stand_all(
    catalog: Catalog,
    board: Board,
    deals: list[Deal],
    held: list[HeldPrize],
    rng: random.Random,
) -> Stood:
    """Every deal that fits, then a fallback prize on each slot the sets left."""
    sets: list[tuple[Deal, list[PlacedObject]]] = []
    taken: set[HeldPrize] = set()
    for deal in deals:
        objs = stand_deal(catalog, board, deal, rng)
        if objs is not None:
            sets.append((deal, objs))
            taken |= {slot.held for slot, _ in deal.parts}
    fallbacks = [stand_fallback(catalog, board, h, rng) for h in held if h not in taken]
    return Stood(sets, fallbacks)
