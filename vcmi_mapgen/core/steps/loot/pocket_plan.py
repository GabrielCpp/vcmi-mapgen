import random
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from vcmi_mapgen.core.catalog import ArtifactTier
from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.planning.content import PlaceIntent, draw_level
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
LEVEL_STEPS = (2500, 6000, 10000, 15000, 20000)

type Candidate = tuple[Tile, frozenset[Tile], frozenset[Tile]]


class PocketKind(StrEnum):
    SHALLOW = "shallow"
    DEEP = "deep"


def pocket_kind(area: int, depth: int) -> PocketKind:
    return PocketKind.DEEP if area >= DEEP_AREA and depth >= DEEP_DEPTH else PocketKind.SHALLOW


def guard_level_for_value(value: int) -> int:
    return 1 + sum(value >= step for step in LEVEL_STEPS)


def ward_tier(rng: random.Random, guard_mean: float) -> ArtifactTier:
    return ART_TIER_BY_GUARD_LEVEL[
        min(len(ART_TIER_BY_GUARD_LEVEL), draw_level(rng, guard_mean)) - 1
    ]


def largest(candidates: Sequence[Candidate]) -> Candidate:
    return max(candidates, key=lambda c: len(c[1]))


def deepest_spots(spots: Iterable[Tile], ref: Tile, n: int) -> list[Tile]:
    ordered = sorted(spots, key=lambda t: max(abs(t[0] - ref[0]), abs(t[1] - ref[1])))
    return ordered[-n:] if n > 0 else []


@dataclass(frozen=True, slots=True)
class PocketPlan:
    guard_means: Mapping[int, float]


def level_plan(
    intents: Mapping[int, PlaceIntent], zone_records: Sequence[ZoneRecord]
) -> PocketPlan | None:
    means = {zr.zid: intents[zr.zid].guard for zr in zone_records if zr.zid in intents}
    return PocketPlan(means) if means else None
