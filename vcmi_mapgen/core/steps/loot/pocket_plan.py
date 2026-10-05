from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.model.artifact import ArtifactTier
from vcmi_mapgen.core.planning.content import PlaceIntent
from vcmi_mapgen.core.planning.zone_index import ZoneRecord

ART_TIER_BY_GUARD_LEVEL: tuple[ArtifactTier, ...] = (
    "treasure",
    "treasure",
    "minor",
    "major",
    "major",
    "relic",
)
DEEP_AREA = 3
DEEP_DEPTH = 2
FILL_CAP = 5
CHEST_SHARE = 1 / 3

type Candidate = tuple[Tile, frozenset[Tile], frozenset[Tile]]


class PocketKind(StrEnum):
    SHALLOW = "shallow"
    DEEP = "deep"


def pocket_kind(area: int, depth: int) -> PocketKind:
    return PocketKind.DEEP if area >= DEEP_AREA and depth >= DEEP_DEPTH else PocketKind.SHALLOW


def ward_tier(guard_level: int) -> ArtifactTier:
    return ART_TIER_BY_GUARD_LEVEL[min(len(ART_TIER_BY_GUARD_LEVEL), guard_level) - 1]


def largest(candidates: Sequence[Candidate]) -> Candidate:
    return max(candidates, key=lambda c: len(c[1]))


def deepest_spots(spots: Iterable[Tile], ref: Tile, n: int) -> list[Tile]:
    ordered = sorted(spots, key=lambda t: max(abs(t[0] - ref[0]), abs(t[1] - ref[1])))
    return ordered[-n:] if n > 0 else []


@dataclass(frozen=True, slots=True)
class PocketPlan:
    zids: frozenset[int]


def level_plan(
    intents: Mapping[int, PlaceIntent], zone_records: Sequence[ZoneRecord]
) -> PocketPlan | None:
    zids = frozenset(zr.zid for zr in zone_records if zr.zid in intents)
    return PocketPlan(zids) if zids else None
