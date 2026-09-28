"""`VcmiCatalog`: the `Catalog` port answered from the VCMI tables."""

from typing import final

from vcmi_mapgen.core.catalog import ArtifactTier, ObjectSpec
from vcmi_mapgen.core.model import Footprint, Identity, Role
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.vcmi import terrain as VT
from vcmi_mapgen.vcmi.catalog import decor as DC
from vcmi_mapgen.vcmi.catalog import objects as OB
from vcmi_mapgen.vcmi.catalog import roles as RO


@final
class VcmiCatalog:
    """Each answer delegates to the table query of `vcmi.catalog.objects` or
    `vcmi.catalog.decor`, or names an animation of `vcmi.catalog.roles`. Decoration answers
    drop `DC.EXCLUDE_DECOR_TYPES`."""

    def terrain_name(self, terrain: int) -> str:
        return VT.name_of(terrain)

    def identity_of(self, animation: str) -> Identity:
        return OB.identity_of(animation)

    def spec(self, kind: str) -> ObjectSpec | None:
        if not OB.has_animation(kind):
            return None
        ident = OB.identity_of(kind)
        return ObjectSpec(
            kind, OB.purpose_of_type(ident.type), ident.footprint, OB.is_blocking(kind)
        )

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

    def artifacts(self, tier: ArtifactTier) -> list[str]:
        return OB.artifacts_by_tier(tier)

    def monsters(self, level: int) -> list[str]:
        return OB.monsters_by_level(level)

    def guard(self, level: int) -> Identity:
        return OB.identity_of(RO.RANDOM_MONSTERS[max(1, min(7, int(level))) - 1])

    def random_artifact(self, tier: ArtifactTier | None) -> Identity:
        anim = RO.RANDOM_ARTIFACT if tier is None else RO.RANDOM_ARTIFACT_BY_TIER[tier]
        return OB.identity_of(anim)

    def random_resource(self) -> Identity:
        return OB.identity_of(RO.RANDOM_RESOURCE)

    def random_town(self) -> Identity:
        return OB.identity_of(RO.RANDOM_TOWN)

    def random_dwelling(self, level: int | None) -> Identity:
        anim = RO.RANDOM_DWELLING if level is None else RO.RANDOM_DWELLINGS[level - 1]
        return OB.identity_of(anim)

    def portals(self) -> list[Identity]:
        return [OB.identity_of(a) for a in RO.PORTALS]

    def border_gates(self) -> list[tuple[Identity, Identity]]:
        return [(OB.identity_of(g), OB.identity_of(k)) for g, k in RO.BORDER_GATES]

    def subterranean_gate(self) -> Identity:
        return OB.identity_of(RO.SUBTERRANEAN_GATE)

    def quest_givers(self, terrain: str | int) -> list[Identity]:
        return sorted(
            (h for h in DC.pool(Purpose.QUEST_GATE, terrain) if h.type == RO.QUEST_GIVER_TYPE),
            key=lambda h: h.animation,
        )

    def spell_scroll(self, spell: str) -> Identity:
        return Identity(
            type="spellScroll",
            subtype=spell,
            animation=RO.SPELL_SCROLL,
            footprint=Footprint.one(Role.VISIT),
        )
