"""The guard toll, the effort bands the reward steps price a place by, and what each band
offers: its artifact class weights, its Pandora's Box grant and its box count. The corpus
sets the toll up to level 7 and the first edges. The toll past level 7 extrapolates the
corpus growth per level, and the rest of the edges grow by the same factor, so a place
behind a stronger guard always lands in a higher band."""

import math
from bisect import bisect_right
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from vcmi_mapgen.core.model.artifact import ArtifactTier

type Basket = Mapping[ArtifactTier, int]

DEFAULT_TOLL = (0, 3, 5, 8, 12, 18, 28, 45, 69, 108, 168)
TOP_GUARD = len(DEFAULT_TOLL) - 1
BANDS = 8
CORPUS_EDGES = (8, 13, 22)
DEFAULT_BASKETS: tuple[Basket, ...] = (
    {"treasure": 3, "minor": 1},
    {"treasure": 1, "minor": 3, "major": 1},
    {"minor": 1, "major": 3, "relic": 1},
    {"major": 1, "relic": 3},
    {"major": 1, "relic": 4},
    {"major": 1, "relic": 6},
    {"major": 1, "relic": 9},
    {"relic": 1},
)


@dataclass(frozen=True, slots=True)
class RewardTier:
    """The odds and amounts of one reward tier: flavour weights for gold, experience and
    creatures, the gold and experience amounts, the creature stack range, and the creature
    levels a stack is drawn from."""

    weights: tuple[int, int, int]
    gold: tuple[int, ...]
    experience: tuple[int, ...]
    creatures: tuple[int, int]
    levels: tuple[int, ...] = (1,)


DEFAULT_GRANTS: tuple[RewardTier, ...] = (
    RewardTier((45, 30, 25), (1000, 1500, 2000), (1500, 2500, 5000), (6, 12), (1, 2)),
    RewardTier((35, 35, 30), (2000, 3000, 5000), (5000, 7500), (4, 8), (3, 4)),
    RewardTier((20, 40, 40), (5000, 7500, 10000), (10000, 15000), (3, 6), (5,)),
    RewardTier((0, 40, 60), (10000,), (20000, 30000), (2, 4), (6, 7)),
    RewardTier((0, 40, 60), (10000, 15000), (20000, 30000), (3, 6), (6, 7)),
    RewardTier((0, 35, 65), (15000,), (30000, 40000), (4, 8), (7,)),
    RewardTier((0, 30, 70), (15000, 20000), (40000, 50000), (6, 10), (7,)),
    RewardTier((0, 25, 75), (20000,), (50000,), (8, 14), (7,)),
)
DEFAULT_BOXES = (0, 0, 1, 1, 1, 2, 2, 2)


def toll_growth(toll: Sequence[int]) -> float:
    """The factor the toll grows by per guard level, read between the weakest and the
    strongest guard."""
    first = next((t for t in toll if t > 0), None)
    if first is None or toll[-1] <= first:
        return 1.0
    steps = len(toll) - 1 - toll.index(first)
    return math.pow(toll[-1] / first, 1 / steps)


def extend_edges(edges: Sequence[int], toll: Sequence[int], bands: int = BANDS) -> tuple[int, ...]:
    """``edges`` grown to ``bands - 1`` of them, each next edge the last one times the
    toll's growth per guard level, so the bands keep pace with the guards."""
    growth = toll_growth(toll)
    out = list(edges)
    for k in range(1, bands - len(edges)):
        out.append(max(round(edges[-1] * growth**k), out[-1] + 1))
    return tuple(out)


DEFAULT_EDGES = extend_edges(CORPUS_EDGES, DEFAULT_TOLL)


@dataclass(frozen=True, slots=True)
class Offer:
    """What one band offers a place: the artifact class weights, the grant of each Pandora's
    Box it holds, and how many boxes it holds beside its rolled prizes."""

    basket: Basket
    grant: RewardTier
    boxes: int = 0


def _no_medians() -> Mapping[ArtifactTier, float]:
    return {}


def _no_counts() -> Mapping[ArtifactTier, int]:
    return {}


def _no_families() -> Mapping[str, tuple[int, ...]]:
    return {}


class BandEdgeError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class EffortPriors:
    """The days a hero spends beating a guard of each level 0..TOP_GUARD, the effort edges
    that split places into BANDS bands, and per band its artifact class weights, its Pandora's
    Box grant and its box count. `medians` is the corpus effort at the pickups of each
    artifact class, and `counts` the pickups behind each median. `families` holds per
    gameplay family the corpus count of objects at each effort in days, the last count
    holding every effort past it."""

    toll: tuple[int, ...] = DEFAULT_TOLL
    edges: tuple[int, ...] = DEFAULT_EDGES
    baskets: tuple[Basket, ...] = DEFAULT_BASKETS
    grants: tuple[RewardTier, ...] = DEFAULT_GRANTS
    boxes: tuple[int, ...] = DEFAULT_BOXES
    medians: Mapping[ArtifactTier, float] = field(default_factory=_no_medians)
    counts: Mapping[ArtifactTier, int] = field(default_factory=_no_counts)
    families: Mapping[str, tuple[int, ...]] = field(default_factory=_no_families)

    def __post_init__(self) -> None:
        if len(self.edges) != BANDS - 1 or any(
            a >= b for a, b in zip(self.edges, self.edges[1:], strict=False)
        ):
            raise BandEdgeError(f"band edges must be {BANDS - 1} rising numbers: {self.edges}")
        for name, rows in (("baskets", self.baskets), ("grants", self.grants)):
            if len(rows) != BANDS:
                raise BandEdgeError(f"there must be {BANDS} band {name}: {len(rows)}")
        if len(self.boxes) != BANDS:
            raise BandEdgeError(f"there must be {BANDS} band box counts: {len(self.boxes)}")

    def band(self, total: int) -> int:
        """The band 1..BANDS of an effort in days."""
        return bisect_right(self.edges, total) + 1

    def offer(self, band: int) -> Offer:
        """What a band 1..BANDS offers a place."""
        i = band - 1
        return Offer(self.baskets[i], self.grants[i], self.boxes[i])
