"""The gold-equivalent value of a placed object and the level of a guard (map-math 5.1).

The table is a fixed modelling guess, never learned. Identities come from the catalog: a
random artifact's tier, a random dwelling's level and a random monster's level are read
by matching the object's kind against what the catalog names for them."""

from collections.abc import Mapping
from dataclasses import dataclass

from vcmi_mapgen.core.catalog import ArtifactTier, Catalog
from vcmi_mapgen.core.model import PlacedObject
from vcmi_mapgen.core.model.purpose import VISIT_PURPOSES, Purpose
from vcmi_mapgen.core.reading.ground import REWARD_PURPOSES, purpose_of

TIERS: tuple[ArtifactTier, ...] = ("treasure", "minor", "major", "relic")
ARTIFACT_VALUE: Mapping[ArtifactTier, int] = {
    "treasure": 2000,
    "minor": 5000,
    "major": 10000,
    "relic": 20000,
}
PURPOSE_VALUE: Mapping[str, int] = {
    Purpose.MINE: 3500,
    Purpose.DWELLING: 2000,
    Purpose.BANK: 5000,
    Purpose.RESOURCE_PILE: 750,
    Purpose.REWARD_PICKUP: 1500,
    **dict.fromkeys(VISIT_PURPOSES, 1500),
}
DWELLING_STEP = 1000
LEVELS = range(1, 8)


@dataclass(frozen=True, slots=True)
class ValueTable:
    """The kinds the catalog names for a random artifact of each tier, a random dwelling
    of each level and a random monster of each level, all lowercased."""

    artifacts: Mapping[str, ArtifactTier]
    dwellings: Mapping[str, int]
    monsters: Mapping[str, int]

    @staticmethod
    def of(catalog: Catalog) -> "ValueTable":
        return ValueTable(
            artifacts={catalog.random_artifact(t).kind.lower(): t for t in TIERS},
            dwellings={catalog.random_dwelling(lv).kind.lower(): lv for lv in LEVELS},
            monsters={catalog.guard(lv).kind.lower(): lv for lv in LEVELS},
        )


def value_of(catalog: Catalog, table: ValueTable, obj: PlacedObject) -> int:
    """The object's gold-equivalent value, zero for anything that is not a reward."""
    purpose = purpose_of(catalog, obj)
    if purpose not in REWARD_PURPOSES:
        return 0
    kind = obj.kind.lower()
    if kind in table.artifacts:
        return ARTIFACT_VALUE[table.artifacts[kind]]
    if kind in table.dwellings:
        return DWELLING_STEP * table.dwellings[kind]
    return PURPOSE_VALUE.get(purpose, 0)


def guard_level(catalog: Catalog, table: ValueTable, obj: PlacedObject) -> int | None:
    """A random monster guard's level, None for a fixed stack or a non-guard."""
    if purpose_of(catalog, obj) != Purpose.GUARD:
        return None
    return table.monsters.get(obj.kind.lower())
