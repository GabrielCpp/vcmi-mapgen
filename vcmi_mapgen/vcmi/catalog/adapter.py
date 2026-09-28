"""`VcmiCatalog`: the `Catalog` port answered from the VCMI tables."""

from typing import final

from vcmi_mapgen.core.catalog import ObjectSpec
from vcmi_mapgen.core.model import Identity
from vcmi_mapgen.vcmi import terrain as VT
from vcmi_mapgen.vcmi.catalog import decor as DC
from vcmi_mapgen.vcmi.catalog import objects as OB


@final
class VcmiCatalog:
    """Each answer delegates to the table query of `vcmi.catalog.objects` or
    `vcmi.catalog.decor`. Decoration answers drop `DC.EXCLUDE_DECOR_TYPES`."""

    def terrain_name(self, terrain: int) -> str:
        return VT.name_of(terrain)

    def identity_of(self, animation: str) -> Identity:
        return OB.identity_of(animation)

    def spec(self, kind: str) -> ObjectSpec | None:
        if not OB.has_animation(kind):
            return None
        ident = OB.identity_of(kind)
        return ObjectSpec(kind, OB.purpose_of_type(ident.type), ident.mask, OB.is_blocking(kind))

    def allowed_on(self, animation: str, terrain: str | int) -> bool:
        return OB.allowed_on(animation, terrain)

    def candidates(self, purpose: str, terrain: str | int) -> list[Identity]:
        return DC.pool(purpose, terrain)

    def decor(
        self, terrain: str | int, *, blocking: bool | None = None, max_cells: int | None = None
    ) -> list[Identity]:
        return DC.decor_pool(
            terrain, blocking=blocking, max_cells=max_cells, exclude_types=DC.EXCLUDE_DECOR_TYPES
        )

    def decor_categories(self) -> list[str]:
        return DC.veg_categories()

    def decor_category(self, animation: str) -> str | None:
        ci = DC.category_of(animation)
        if ci is None:
            return None
        cat = DC.veg_categories()[ci]
        return None if cat in DC.EXCLUDE_DECOR_TYPES else cat

    def mines_by_resource(self, terrain: str | int) -> dict[str, list[Identity]]:
        return OB.mines_by_resource(terrain)

    def spells(self, level: int) -> list[str]:
        return OB.spells_by_level(level)
