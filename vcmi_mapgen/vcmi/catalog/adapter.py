"""`VcmiCatalog`: the `Catalog` port answered from the VCMI tables."""

from collections.abc import Sequence
from typing import final

from vcmi_mapgen.core.catalog import Crossing, HeroPace, ObjectSpec, Trait
from vcmi_mapgen.core.model import Footprint, Identity, Role
from vcmi_mapgen.core.model.artifact import ArtifactSet, ArtifactTier
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.vcmi import terrain as VT
from vcmi_mapgen.vcmi.catalog import decor as DC
from vcmi_mapgen.vcmi.catalog import objects as OB
from vcmi_mapgen.vcmi.catalog import roles as RO
from vcmi_mapgen.vcmi.catalog import tables as TB
from vcmi_mapgen.vcmi.content.enabled import BASE_GAME, EnabledSet
from vcmi_mapgen.vcmi.content.mods import NO_MODS, ModContent
from vcmi_mapgen.vcmi.content.objects import ModObject
from vcmi_mapgen.vcmi.tiles import THIN_DRAWABLE


def _name(terrain: str | int) -> str:
    return terrain if isinstance(terrain, str) else VT.name_of(terrain)


@final
class VcmiCatalog:
    """Each answer delegates to the table query of `vcmi.catalog.objects` or
    `vcmi.catalog.decor`, or names an animation of `vcmi.catalog.roles`. Decoration answers
    drop `DC.EXCLUDE_DECOR_TYPES`. Every pool and name list drops what the enabled set
    bans, by object type, subtype or animation, or by creature, artifact or spell name.
    Objects the enabled mods declare answer from ``mods`` and join each pool after the base
    game's."""

    def __init__(self, enabled: EnabledSet = BASE_GAME, mods: ModContent = NO_MODS) -> None:
        self.enabled = enabled
        self.mods = mods

    def _kept[T: Identity | str](self, items: list[T]) -> list[T]:
        if not self.enabled.banned:
            return items
        return [i for i in items if self._allows(i)]

    def _allows(self, item: Identity | str) -> bool:
        if isinstance(item, str):
            return self.enabled.allows(item)
        return self.enabled.allows(item.type, item.subtype, item.kind)

    def _sets(self, sets: Sequence[ArtifactSet]) -> list[ArtifactSet]:
        return [s for s in sets if self.enabled.allows(s.name, *s.parts)]

    def terrain_name(self, terrain: int) -> str:
        return VT.name_of(terrain)

    def identity_of(self, animation: str) -> Identity:
        entry = self.mods.object(animation)
        return OB.identity_of(animation) if entry is None else entry.identity

    def spec(self, kind: str) -> ObjectSpec | None:
        entry = self.mods.object(kind)
        if entry is not None:
            return self._mod_spec(entry) if self._allows(entry.identity) else None
        if not OB.has_animation(kind) or not self._allows(OB.identity_of(kind)):
            return None
        ident = OB.identity_of(kind)
        return ObjectSpec(
            kind, OB.purpose_of_type(ident.type), ident.footprint, OB.is_blocking(kind)
        )

    def _mod_spec(self, entry: ModObject) -> ObjectSpec:
        fp = entry.identity.footprint
        blocking = any(role.blocks for _, _, role in fp.cells)
        return ObjectSpec(entry.identity.kind, entry.purpose, fp, blocking)

    def allowed_on(self, animation: str, terrain: str | int) -> bool:
        entry = self.mods.object(animation)
        if entry is None:
            return OB.allowed_on(animation, terrain)
        return entry.stands_on(_name(terrain))

    def candidates(self, purpose: str, terrain: str | int) -> list[Identity]:
        base = DC.pool(purpose, terrain)
        if self.mods.objects:
            base = [*base, *self.mods.pool(purpose, _name(terrain))]
        return self._kept(base)

    def decor(
        self, terrain: str | int, *, blocking: bool | None = None, max_cells: int | None = None
    ) -> list[Identity]:
        pool = DC.decor_pool(
            terrain, blocking=blocking, max_cells=max_cells, exclude_types=DC.EXCLUDE_DECOR_TYPES
        )
        return self._kept(pool)

    def decor_categories(self) -> list[str]:
        return DC.veg_categories()

    def decor_category(self, animation: str) -> str | None:
        ci = DC.category_of(animation)
        if ci is None:
            return None
        cat = DC.veg_categories()[ci]
        return None if cat in DC.EXCLUDE_DECOR_TYPES else cat

    def mines_by_resource(self, terrain: str | int) -> dict[str, list[Identity]]:
        mines = OB.mines_by_resource(terrain)
        return {res: self._kept(ids) for res, ids in mines.items() if res not in RO.ABANDONED_MINES}

    def types_with(self, trait: Trait) -> tuple[str, ...]:
        return RO.TRAIT_TYPES[trait]

    def spells(self, level: int) -> list[str]:
        return self._kept(OB.spells_by_level(level))

    def artifacts(self, tier: ArtifactTier) -> list[str]:
        return self._kept(OB.artifacts_by_tier(tier))

    def artifact_sets(self) -> list[ArtifactSet]:
        sets = OB.artifact_set_table()
        return self._sets(sets) if self.enabled.banned else sets

    def artifact(self, name: str) -> Identity | None:
        return OB.artifact_pickup(name) if self.enabled.allows(name) else None

    def monsters(self, level: int) -> list[str]:
        return self._kept(OB.monsters_by_level(level))

    def creature_level(self, kind: str) -> int | None:
        type_name, _, _ = OB.static_type(kind)
        if type_name in RO.MONSTER_LEVELS:
            return RO.MONSTER_LEVELS[type_name]
        if type_name != RO.MONSTER_TYPE:
            return None
        level = TB.monster_levels().get(OB.identity_of(kind).subtype or "", 0)
        return min(7, level) if level >= 1 else None

    def guard(self, level: int) -> Identity:
        return OB.identity_of(RO.RANDOM_MONSTERS[max(1, min(7, int(level))) - 1])

    def random_artifact(self, tier: ArtifactTier) -> Identity:
        return OB.identity_of(RO.RANDOM_ARTIFACT_BY_TIER[tier])

    def random_resource(self) -> Identity:
        return OB.identity_of(RO.RANDOM_RESOURCE)

    def random_town(self) -> Identity:
        return OB.identity_of(RO.RANDOM_TOWN)

    def random_dwelling(self, level: int | None) -> Identity:
        anim = RO.RANDOM_DWELLING if level is None else RO.RANDOM_DWELLINGS[level - 1]
        return OB.identity_of(anim)

    def portals(self) -> list[Identity]:
        return self._kept([OB.identity_of(a) for a in RO.PORTALS])

    def border_gates(self) -> list[tuple[Identity, Identity]]:
        pairs = [(OB.identity_of(g), OB.identity_of(k)) for g, k in RO.BORDER_GATES]
        return [(g, k) for g, k in pairs if self._allows(g) and self._allows(k)]

    def subterranean_gate(self) -> Identity:
        return OB.identity_of(RO.SUBTERRANEAN_GATE)

    def quest_givers(self, terrain: str | int) -> list[Identity]:
        return sorted(
            (
                h
                for h in self.candidates(Purpose.QUEST_GATE, terrain)
                if h.type == RO.QUEST_GIVER_TYPE
            ),
            key=lambda h: h.kind,
        )

    def spell_scroll(self, spell: str) -> Identity:
        return Identity(
            type=RO.TRAIT_TYPES[Trait.SCROLL][0],
            subtype=spell,
            kind=RO.SPELL_SCROLL,
            footprint=Footprint.one(Role.VISIT),
        )

    def crossing(self, kind: str) -> tuple[Crossing, int] | None:
        type_name, cls, sub = OB.static_type(kind)
        crossing = RO.CROSSINGS.get(type_name or "")
        if crossing is None or cls is None or sub is None:
            return None
        return crossing, cls * 256 + sub if crossing is Crossing.TELEPORT else sub

    def pace(self) -> HeroPace:
        table = TB.hero_pace()
        cost = {t: table["cost"][VT.name_of(t)] for t in Terrain if VT.name_of(t) in table["cost"]}
        return HeroPace(land=table["land"], sea=table["sea"], cost=cost)

    def thin_terrains(self) -> frozenset[Terrain]:
        return THIN_DRAWABLE
