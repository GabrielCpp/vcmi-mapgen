"""The fitted odds of water on each surface tile and the corpus maps' water targets."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WaterTarget:
    """One corpus map's water: its share of the surface, its share of the map edge, and its
    land masses above 5% of the land."""

    share: float
    edge: float
    masses: int


@dataclass(frozen=True, slots=True)
class WaterPriors:
    """The logistic coefficients over the water features, ``beta`` with the neighbour terms
    and ``static_beta`` without them, and one target per corpus map."""

    beta: tuple[float, ...] = ()
    static_beta: tuple[float, ...] = ()
    targets: tuple[WaterTarget, ...] = ()
