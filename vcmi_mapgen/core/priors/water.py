"""The fitted odds of water on each surface tile and the corpus maps' water targets."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WaterTarget:
    """One corpus map's water: its share of the surface, its share of the map edge, its
    land masses above 5% of the land, and the water tiles its water decoration blocks per
    water tile."""

    share: float
    edge: float
    masses: int
    dress: float = 0.0


@dataclass(frozen=True, slots=True)
class WaterPriors:
    """The logistic coefficients over the water features, ``beta`` with the neighbour terms
    and ``static_beta`` without them, one target per corpus map, and how many water
    decorations of each kind the corpus maps with water hold."""

    beta: tuple[float, ...] = ()
    static_beta: tuple[float, ...] = ()
    targets: tuple[WaterTarget, ...] = ()
    dress_kinds: tuple[tuple[str, int], ...] = ()
