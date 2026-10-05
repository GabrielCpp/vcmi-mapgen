"""The content intent of each place (map-math 5.1 and 5.2): the player homes in owner order,
and for every place its role, its hop count from the nearest home, how much reward it holds
against the map's mean and the mean level of its guards.

A ``ContentPlanner`` is the role ``cli/steps.py`` picks per terrain model. ``NoContent``
plans nothing, so every consumer keeps its own default. ``HopContent`` reads the planned
places and the corpus content table of each level."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol, final

from vcmi_mapgen.core.priors.places import PlaceContent, PlaceStats
from vcmi_mapgen.core.reading.content import UNREACHED, hops
from vcmi_mapgen.core.reading.places import PlaceRole

HOP_CAP = 4
TILE_PRIOR = 2000.0
GUARD_PRIOR = 30.0
LEVEL_MIN = 1
LEVEL_MAX = 7

type ZoneKey = tuple[int, int]


class PlaceNode(Protocol):
    @property
    def role(self) -> PlaceRole: ...

    @property
    def owner(self) -> int | None: ...


class PlaceGraph(Protocol):
    @property
    def places(self) -> Mapping[int, PlaceNode]: ...

    @property
    def passable(self) -> frozenset[tuple[int, int]]: ...


@dataclass(frozen=True, slots=True)
class PlaceIntent:
    """One place's role, its hop count from the nearest home (UNREACHED when no home
    reaches it), its reward per tile against the map's mean, and its guards' mean level."""

    role: str
    hop: int
    scale: float
    guard: float


@dataclass(frozen=True, slots=True)
class ContentPlan:
    """The player homes as ``(level, zid)`` in owner order and each planned place's intent.
    The empty plan leaves every consumer on its own default."""

    homes: tuple[ZoneKey, ...] = ()
    intents: Mapping[ZoneKey, PlaceIntent] = field(default_factory=dict[ZoneKey, PlaceIntent])


def hop_bin(hop: int) -> int:
    return hop if hop == UNREACHED else min(hop, HOP_CAP)


@dataclass(slots=True)
class PlaceSums:
    tiles: int = 0
    value: int = 0
    guards: int = 0
    levels: int = 0

    def add(self, row: PlaceContent) -> None:
        self.tiles += row.area
        self.value += row.value
        self.guards += len(row.guards)
        self.levels += sum(row.guards)

    def value_rate(self, prior: float) -> float:
        return (self.value + TILE_PRIOR * prior) / (self.tiles + TILE_PRIOR)

    def guard_mean(self, prior: float) -> float:
        return (self.levels + GUARD_PRIOR * prior) / (self.guards + GUARD_PRIOR)


@dataclass(frozen=True, slots=True)
class ContentTable:
    """The corpus value per tile and mean random guard level of one level, by role and hop
    bin. Each cell is shrunk toward its hop bin, and each hop bin
    toward the whole level, so a sparse cell reads close to the cells around it."""

    total: PlaceSums
    by_hop: Mapping[int, PlaceSums]
    by_cell: Mapping[tuple[str, int], PlaceSums]

    @staticmethod
    def of(rows: Sequence[PlaceContent]) -> "ContentTable":
        total = PlaceSums()
        by_hop: dict[int, PlaceSums] = {}
        by_cell: dict[tuple[str, int], PlaceSums] = {}
        for row in rows:
            h = hop_bin(row.hop)
            for sums in (
                total,
                by_hop.setdefault(h, PlaceSums()),
                by_cell.setdefault((row.role, h), PlaceSums()),
            ):
                sums.add(row)
        return ContentTable(total, by_hop, by_cell)

    def intent(self, role: str, hop: int) -> PlaceIntent:
        h = hop_bin(hop)
        value = self.total.value / max(1, self.total.tiles)
        guard = self.total.levels / max(1, self.total.guards)
        marginal = self.by_hop.get(h, PlaceSums())
        cell = self.by_cell.get((role, h), PlaceSums())
        v_hop, g_hop = marginal.value_rate(value), marginal.guard_mean(guard)
        scale = cell.value_rate(v_hop) / value if value > 0 else 1.0
        return PlaceIntent(role, hop, scale, cell.guard_mean(g_hop))


class ContentPlanner(Protocol):
    def plan(
        self, stats: Mapping[int, PlaceStats], levels: Mapping[int, PlaceGraph]
    ) -> ContentPlan:
        """The content plan of the planned ``levels``, read against each level's corpus
        place statistics ``stats``."""
        ...


@final
class NoContent:
    """The markov terrain's planner: it plans nothing."""

    def plan(
        self, stats: Mapping[int, PlaceStats], levels: Mapping[int, PlaceGraph]
    ) -> ContentPlan:
        _ = stats, levels
        return ContentPlan()


def level_intents(table: ContentTable, graph: PlaceGraph) -> dict[int, PlaceIntent]:
    """Each place's intent, its hop count read over the borders that are not closed from the
    owned homes of its level."""
    homes = [p for p, place in graph.places.items() if place.owner is not None]
    hop = hops(graph.passable, homes)
    return {
        p: table.intent(place.role.value, hop.get(p, UNREACHED))
        for p, place in sorted(graph.places.items())
    }


def owned_homes(levels: Mapping[int, PlaceGraph]) -> tuple[ZoneKey, ...]:
    """Every owned place as ``(level, zid)``, by owner."""
    owned = [
        (place.owner, level, p)
        for level, graph in levels.items()
        for p, place in graph.places.items()
        if place.owner is not None
    ]
    return tuple((level, p) for _owner, level, p in sorted(owned))


@final
class HopContent:
    """The places terrain's planner: the owned homes, each place's intent read off the
    corpus content table of its level by its role and its hop count from home."""

    def plan(
        self, stats: Mapping[int, PlaceStats], levels: Mapping[int, PlaceGraph]
    ) -> ContentPlan:
        intents: dict[ZoneKey, PlaceIntent] = {}
        for level, graph in sorted(levels.items()):
            level_stats = stats.get(level)
            if level_stats is None or not level_stats.content:
                continue
            table = ContentTable.of(level_stats.content)
            for p, intent in level_intents(table, graph).items():
                intents[level, p] = intent
        return ContentPlan(owned_homes(levels), intents)
