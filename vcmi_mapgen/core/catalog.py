"""The `Catalog` port: every question the core asks about objects.

A step receives one `Catalog` in `run` and hands it to the functions that decide. Every
parameter and return is a core type. Lists come back in a fixed order, because every draw
depends on it. `vcmi.catalog.adapter.VcmiCatalog` is the production implementation.

`terrain_name` is transitional. The corpus priors are keyed by the VCMI terrain name until
`s24b` loads them as values keyed by `Terrain`.
"""

from dataclasses import dataclass
from typing import Protocol

from vcmi_mapgen.core.model import Identity, Mask
from vcmi_mapgen.core.model.purpose import Purpose


@dataclass(frozen=True, slots=True)
class ObjectSpec:
    """What the catalog knows about one object kind: the purpose it is placed for, its
    footprint mask and whether it blocks movement."""

    kind: str
    purpose: Purpose | None
    mask: Mask
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
