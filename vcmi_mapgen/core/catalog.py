"""The `Catalog` port: every question the core asks about objects.

A step receives one `Catalog` in `run` and hands it to the functions that decide. Every
parameter and return is a core type. Lists come back in a fixed order, because every draw
depends on it. `vcmi.catalog.adapter.VcmiCatalog` is the production implementation.

`terrain_name` is transitional. The corpus priors are keyed by the VCMI terrain name until
`s24b` loads them as values keyed by `Terrain`.
"""

from dataclasses import dataclass
from typing import Literal, Protocol

from vcmi_mapgen.core.model import Footprint, Identity
from vcmi_mapgen.core.model.purpose import Purpose

type ArtifactTier = Literal["treasure", "minor", "major", "relic"]


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
        """The mine identities on a terrain, grouped by the resource they yield."""
        ...

    def spells(self, level: int) -> list[str]:
        """The spells of one mage-guild level, sorted."""
        ...

    def artifacts(self, tier: ArtifactTier) -> list[str]:
        """The artifacts of one rarity tier, sorted."""
        ...

    def monsters(self, level: int) -> list[str]:
        """The creatures of one town tier, sorted."""
        ...

    def guard(self, level: int) -> Identity:
        """The random monster of a strength level, clamped to 1..7."""
        ...

    def random_artifact(self, tier: ArtifactTier | None) -> Identity:
        """The random artifact of a rarity tier, or of any tier for None."""
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
