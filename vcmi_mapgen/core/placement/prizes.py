"""The prizes of a cut-off place: artifacts drawn by the band's basket, Pandora's Boxes with
the band's grant, chests, scrolls and rare resources, every one a pickup a hero collects."""

from __future__ import annotations

import random
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Self

from vcmi_mapgen.core.catalog import Catalog, Trait
from vcmi_mapgen.core.model import Identity, Tile
from vcmi_mapgen.core.model.artifact import TIERS, ArtifactTier
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.model.resource import Resource
from vcmi_mapgen.core.placement.place import PlaceSpec, PlaceTarget, place_one
from vcmi_mapgen.core.placement.rewards import Creatures, creatures_of, draw_reward
from vcmi_mapgen.core.priors.effort import Basket, Offer, RewardTier

SCROLL_LEVELS = (4, 5)
RARE_RESOURCES = frozenset(
    {Resource.MERCURY, Resource.SULFUR, Resource.CRYSTAL, Resource.GEMS, Resource.GOLD}
)


@dataclass(frozen=True, slots=True)
class PrizePools:
    """The pickups a place of one terrain draws its prizes from, the Pandora's Boxes among
    them, and the creatures of each level a box grants."""

    pool_art: list[Identity]
    pool_res: list[Identity]
    chest_kind_pools: dict[str, list[Identity]]
    arts: Mapping[ArtifactTier, Identity]
    pool_rare: list[Identity]
    boxes: list[Identity]
    creatures: Creatures

    @classmethod
    def of(cls, catalog: Catalog, terrain: str) -> Self:
        pool_art = [
            i
            for i in catalog.candidates(Purpose.REWARD_PICKUP, terrain)
            if i.type not in catalog.types_with(Trait.MEAGER)
        ]
        pool_res = catalog.candidates(Purpose.RESOURCE_PILE, terrain)
        kinds = catalog.types_with(Trait.CHEST) + catalog.types_with(Trait.ZONE_CHEST)
        pool_chest = [i for i in pool_art if i.type in kinds]
        chest_kind_pools = {kind: [i for i in pool_chest if i.type == kind] for kind in kinds}
        chest_kind_pools[Trait.SCROLL] = [
            catalog.spell_scroll(n) for lvl in SCROLL_LEVELS for n in catalog.spells(lvl)
        ]
        return cls(
            pool_art=pool_art,
            pool_res=pool_res,
            chest_kind_pools=chest_kind_pools,
            arts={t: catalog.random_artifact(t) for t in TIERS},
            pool_rare=[i for i in pool_res if i.subtype in RARE_RESOURCES],
            boxes=[i for i in pool_art if i.type in catalog.types_with(Trait.REWARD_BOX)],
            creatures=creatures_of(catalog),
        )

    def chest_kinds(self) -> list[str]:
        return [k for k, p in self.chest_kind_pools.items() if p]


def basket_artifact(
    rng: random.Random, arts: Mapping[ArtifactTier, Identity], basket: Basket
) -> Identity | None:
    """The random artifact of a class drawn by the basket's weights."""
    tiers: list[ArtifactTier] = [t for t in TIERS if basket.get(t, 0) > 0 and t in arts]
    if not tiers:
        return None
    return arts[rng.choices(tiers, weights=[basket[t] for t in tiers], k=1)[0]]


def artifact_spec(rng: random.Random, pools: PrizePools, basket: Basket) -> PlaceSpec | None:
    """A basket artifact, None when the basket weighs no class the catalog has."""
    ident = basket_artifact(rng, pools.arts, basket)
    if ident is None:
        return None
    return PlaceSpec(
        Purpose.REWARD_PICKUP, pools.pool_art, ident=ident, cache=True, interactive_only=True
    )


def box_spec(
    rng: random.Random, pools: PrizePools, grant: RewardTier, ident: Identity | None = None
) -> PlaceSpec | None:
    """A Pandora's Box that grants a reward drawn at ``grant``, None when the terrain has no
    box."""
    if ident is None and not pools.boxes:
        return None
    box = ident if ident is not None else rng.choice(pools.boxes)
    payload = draw_reward(rng, grant, pools.creatures)
    return PlaceSpec(
        Purpose.REWARD_PICKUP,
        pools.pool_art,
        ident=box,
        cache=True,
        payload=payload,
        interactive_only=True,
    )


def roll_spec(rng: random.Random, pools: PrizePools, offer: Offer) -> PlaceSpec | None:
    """One rolled prize: a basket artifact, a chest or scroll, or a rare resource. A rolled
    Pandora's Box grants the band's reward."""
    roll = rng.random()
    if roll < 0.2 and (spec := artifact_spec(rng, pools, offer.basket)) is not None:
        return spec
    chest_kinds = pools.chest_kinds()
    if roll < 0.6 and chest_kinds:
        ident = rng.choice(pools.chest_kind_pools[rng.choice(chest_kinds)])
        if ident in pools.boxes:
            return box_spec(rng, pools, offer.grant, ident)
        return PlaceSpec(
            Purpose.REWARD_PICKUP, pools.pool_art, ident=ident, cache=True, interactive_only=True
        )
    return rare_spec(rng, pools)


def rare_spec(rng: random.Random, pools: PrizePools) -> PlaceSpec | None:
    if not pools.pool_rare:
        return None
    return PlaceSpec(
        Purpose.RESOURCE_PILE,
        pools.pool_res,
        ident=rng.choice(pools.pool_rare),
        cache=True,
        interactive_only=True,
    )


def fallback_specs(rng: random.Random, pools: PrizePools, offer: Offer) -> list[PlaceSpec]:
    """The rolled prize, then a rare resource, then any resource."""
    specs = [
        roll_spec(rng, pools, offer),
        rare_spec(rng, pools),
        PlaceSpec(Purpose.RESOURCE_PILE, pools.pool_res, cache=True, interactive_only=True),
    ]
    return [s for s in specs if s is not None]


@dataclass(frozen=True, slots=True)
class HeldPrize:
    """A prize slot a place holds back for the set dealer: its level and tile, the terrain
    whose pools fill it, and the artifact the place would have put there."""

    level: int
    tile: Tile
    terrain: str
    fallback: Identity


@dataclass(frozen=True, slots=True)
class Hold:
    """A slot one placement pass held back, and the artifact it falls back to."""

    tile: Tile
    fallback: Identity

    def at(self, level: int, terrain: str) -> HeldPrize:
        return HeldPrize(level, self.tile, terrain, self.fallback)


def hold_prize(target: PlaceTarget, spec: PlaceSpec, tiles: Iterable[Tile]) -> Hold | None:
    """Hold the first tile where ``spec`` lands. The prize leaves ``target.objs`` and stays in
    the cover with its claim, so the rest of the pass keeps clear of the slot."""
    if spec.ident is None:
        return None
    for t in tiles:
        if place_one(target, spec, *t):
            _ = target.objs.pop()
            return Hold(t, spec.ident)
    return None


@dataclass(frozen=True, slots=True)
class Prizes:
    """What one prize pass left: the held slot, when one landed, and the tiles that took a
    rolled prize."""

    held: Hold | None
    placed: list[Tile]

    def took(self) -> set[Tile]:
        return {*self.placed, *((self.held.tile,) if self.held else ())}


def place_boxes(
    target: PlaceTarget, pools: PrizePools, offer: Offer, tiles: Sequence[Tile]
) -> list[Tile]:
    """The band's Pandora's Boxes, each on the first of ``tiles`` that takes it."""
    placed: list[Tile] = []
    for _ in range(offer.boxes):
        spec = box_spec(target.rng, pools, offer.grant)
        if spec is None:
            break
        t = next((t for t in tiles if t not in placed and place_one(target, spec, *t)), None)
        if t is None:
            break
        placed.append(t)
    return placed


def place_prizes(
    target: PlaceTarget, pools: PrizePools, offer: Offer, tiles: Sequence[Tile], count: int
) -> Prizes:
    """Up to ``count`` prizes on ``tiles`` in order: the first tile that takes a basket
    artifact is held back for the set dealer, the band's Pandora's Boxes come next, and
    rolled prizes take the rest."""
    rng = target.rng
    head = artifact_spec(rng, pools, offer.basket) if count > 0 else None
    held = hold_prize(target, head, tiles) if head is not None else None
    room = max(count - (held is not None), 0)
    boxes = place_boxes(target, pools, replace(offer, boxes=min(offer.boxes, room)), tiles)
    placed: list[Tile] = list(boxes)
    for t in tiles:
        if len(placed) + (held is not None) >= count:
            break
        if (held is not None and t == held.tile) or t in boxes:
            continue
        if any(place_one(target, spec, *t) for spec in fallback_specs(rng, pools, offer)):
            placed.append(t)
    return Prizes(held, placed)
