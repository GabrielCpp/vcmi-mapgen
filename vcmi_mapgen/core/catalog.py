"""The `Catalog` port: every question the core asks about objects.

A step receives one `Catalog` in `run` and hands it to the functions that decide. Every
parameter and return is a core type. Lists come back in a fixed order, because every draw
depends on it. `vcmi.catalog.adapter.VcmiCatalog` is the production implementation.

`terrain_name` is transitional. The corpus priors are keyed by the VCMI terrain name until
`s24b` loads them as values keyed by `Terrain`.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from vcmi_mapgen.core.model import Footprint, Identity
from vcmi_mapgen.core.model.artifact import ArtifactSet, ArtifactTier
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.model.terrain import Terrain


class Trait(StrEnum):
    """A kind of object some decision singles out. The catalog says which object types
    carry each trait, so the core never names a type.

    `REWARD_BOX` draws a reward when placed. `SCROLL` carries the spell its subtype names.
    `SHIPYARD` builds boats. `ARTIFACT` is one artifact pickup. `SPACED` keeps a distance
    from its twins in pockets. `LUCK` stays out of the loot fill. `MEAGER` is a pickup too
    poor for an artifact slot. `HERO_BOOST` strengthens the visiting hero. `CHEST` and
    `ZONE_CHEST` are the chest kinds, the second drawn only in loot zones.
    `RANDOM_DWELLING` resolves to a dwelling of the town it is tied to."""

    REWARD_BOX = "reward_box"
    SCROLL = "scroll"
    SHIPYARD = "boat_builder"
    ARTIFACT = "artifact_pickup"
    SPACED = "spaced"
    LUCK = "luck"
    MEAGER = "meager"
    HERO_BOOST = "hero_boost"
    CHEST = "chest"
    ZONE_CHEST = "zone_chest"
    RANDOM_DWELLING = "random_dwelling"


class Crossing(StrEnum):
    """What an object does to a route that meets it. `GATE` lets through a hero who holds
    the key of its channel, and `TENT` hands that key. `TELEPORT` sends the hero to another
    end of its channel. `ONE_WAY_IN` sends the hero to a `ONE_WAY_OUT` of its channel.
    `UNDERGROUND` joins the nearest gate on the other level. `SHIPYARD` builds a boat on the
    water beside it, and `BOAT` is one already afloat."""

    GATE = "gate"
    TENT = "tent"
    TELEPORT = "teleport"
    ONE_WAY_IN = "one_way_in"
    ONE_WAY_OUT = "one_way_out"
    UNDERGROUND = "underground"
    SHIPYARD = "boat_builder"
    BOAT = "afloat"


@dataclass(frozen=True, slots=True)
class HeroPace:
    """How far the slowest starting hero moves: its movement points per day on land and at
    sea, and what one straight step costs on each terrain it can cross."""

    land: int
    sea: int
    cost: Mapping[Terrain, int]


@dataclass(frozen=True, slots=True)
class ObjectSpec:
    """What the catalog knows about one object kind: the purpose it is placed for, its
    footprint and whether it blocks movement."""

    kind: str
    purpose: Purpose | None
    footprint: Footprint
    blocking: bool


class Catalog(Protocol):
    def terrain_name(self, terrain: int) -> str:
        """The key the corpus priors use for a terrain, or "" for an unknown code."""
        ...

    def identity_of(self, animation: str) -> Identity:
        """The identity of one animation."""
        ...

    def spec(self, kind: str) -> ObjectSpec | None:
        """The spec of one object kind, or None when the catalog does not know it."""
        ...

    def allowed_on(self, animation: str, terrain: str | int) -> bool:
        """Whether an animation may stand on a terrain."""
        ...

    def candidates(self, purpose: str, terrain: str | int) -> list[Identity]:
        """The objects serving a purpose that may stand on a terrain."""
        ...

    def decor(
        self, terrain: str | int, *, blocking: bool | None = None, max_cells: int | None = None
    ) -> list[Identity]:
        """The decoration candidates for a terrain, water features left out."""
        ...

    def decor_categories(self) -> list[str]:
        """Every decoration category, water features included."""
        ...

    def decor_category(self, animation: str) -> str | None:
        """The decoration category of an animation, or None when it is not decoration or is a
        water feature."""
        ...

    def mines_by_resource(self, terrain: str | int) -> dict[str, list[Identity]]:
        """The mine identities on a terrain, grouped by the resource they yield. Abandoned
        mines yield no fixed resource and are left out."""
        ...

    def abandoned_mines(self, terrain: str | int) -> list[Identity]:
        """The abandoned mine identities on a terrain, by kind."""
        ...

    def types_with(self, trait: Trait) -> tuple[str, ...]:
        """The object types that carry a trait, in the catalog's order."""
        ...

    def spells(self, level: int) -> list[str]:
        """The spells of one mage-guild level, sorted."""
        ...

    def artifacts(self, tier: ArtifactTier) -> list[str]:
        """The artifacts of one rarity tier, sorted."""
        ...

    def artifact_sets(self) -> list[ArtifactSet]:
        """The combined artifacts whose parts all carry a rarity tier, by name."""
        ...

    def artifact(self, name: str) -> Identity | None:
        """The pickup that places one named artifact, or None when the catalog has none."""
        ...

    def monsters(self, level: int) -> list[str]:
        """The creatures of one town tier, sorted."""
        ...

    def creature_level(self, kind: str) -> int | None:
        """The level 1..7 of a monster stack, fixed or random, or None when the kind is no
        monster or a random monster of any level."""
        ...

    def dwelling_level(self, kind: str) -> int | None:
        """The highest creature level a fixed dwelling recruits, unclamped, so a dragon
        dwelling reads above 7. None when the kind recruits no known creature."""
        ...

    def guard(self, level: int) -> Identity:
        """The random monster of a strength level, clamped to 1..7."""
        ...

    def random_artifact(self, tier: ArtifactTier) -> Identity:
        """The random artifact of a rarity tier. `relic` is the one top tier."""
        ...

    def random_resource(self) -> Identity:
        """The random resource pile."""
        ...

    def random_town(self) -> Identity:
        """The random town."""
        ...

    def random_dwelling(self, level: int | None) -> Identity:
        """The random dwelling of a creature level 1..7, or of any level for None."""
        ...

    def portals(self) -> list[Identity]:
        """The two-way portal kinds, in pairing order."""
        ...

    def border_gates(self) -> list[tuple[Identity, Identity]]:
        """The border gate and its keymaster tent, one pair per key colour, in colour order."""
        ...

    def subterranean_gate(self) -> Identity:
        """The gate that joins the surface to the underground."""
        ...

    def quest_givers(self, terrain: str | int) -> list[Identity]:
        """The kinds that can hold a quest on a terrain, in animation order."""
        ...

    def spell_scroll(self, spell: str) -> Identity:
        """The spell scroll that carries one spell."""
        ...

    def crossing(self, kind: str) -> tuple[Crossing, int] | None:
        """The crossing an object kind makes and the channel that pairs its ends, or None
        when a route walks around it."""
        ...

    def pace(self) -> HeroPace:
        """How far the slowest starting hero moves in a day."""
        ...

    def thin_terrains(self) -> frozenset[Terrain]:
        """The terrains whose tile art can draw a strip one tile wide. Despeckle erodes
        thin strips of every other terrain."""
        ...
