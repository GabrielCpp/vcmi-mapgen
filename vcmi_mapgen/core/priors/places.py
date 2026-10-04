"""The corpus place statistics of one level, pooled over the places inferred on every
corpus map (map-math 3.4)."""

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class PlaceCount:
    """One corpus level: its place count, the map's player count and its land area."""

    places: int
    players: int
    land: int


@dataclass(frozen=True, slots=True)
class PaletteCount:
    """One corpus level: its palette region count, its place count and its land area. A
    palette region is a connected component of the places of one dominant terrain on the
    realised place adjacency."""

    regions: int
    places: int
    land: int


@dataclass(frozen=True, slots=True)
class PlaceContent:
    """The content of one place: its role, its hop count from the nearest home on the
    walkable place adjacency (-1 when no home reaches it), its area, its reward count and
    their summed gold-equivalent value, the level of each random-monster guard standing in
    it, and its fixed-stack guard count."""

    role: str
    hop: int
    area: int
    rewards: int
    value: int
    guards: tuple[int, ...] = ()
    fixed: int = 0


@dataclass(frozen=True, slots=True)
class RoadCount:
    """One corpus level's roads: its road tiles, its walkable tiles, its towns, the towns
    with a road tile within two tiles of their anchor, the towns whose road reaches another
    town, its home towns and the home towns with a road."""

    road: int
    walk: int
    towns: int
    joined: int
    linked: int
    homes: int
    home_joined: int


@dataclass(frozen=True, slots=True)
class RoadStats:
    """The road statistics pooled over the corpus levels. ``crossed`` maps
    ``"roleA|roleB|kind"`` to (pairs a road crosses, all pairs) over the levels that carry a
    road. ``surface`` counts road
    tiles by road index per hop of their place from the nearest home, capped at 4, with -1
    for a place no home reaches. ``on_dominant`` is (road tiles on their place's dominant,
    road tiles), ``land_dominant`` the same over all land, and ``near`` is (reward objects
    within two tiles of a road, reward objects)."""

    counts: tuple[RoadCount, ...] = ()
    crossed: Mapping[str, tuple[int, int]] = field(default_factory=dict[str, tuple[int, int]])
    surface: Mapping[int, Mapping[int, int]] = field(default_factory=dict[int, Mapping[int, int]])
    on_dominant: tuple[int, int] = (0, 0)
    land_dominant: tuple[int, int] = (0, 0)
    near: tuple[int, int] = (0, 0)


@dataclass(frozen=True, slots=True)
class PlaceStats:
    """Samples and tallies over the inferred places of one level. Keys of the per-role
    maps are role names. ``adjacency`` counts ``"roleA|roleB|kind"`` with roleA <= roleB.
    ``border_kinds`` counts ``"kind|same|border"`` and ``"kind|diff|border"``, where same
    means the two places share a dominant terrain. ``dominant`` counts terrain codes.

    The paint statistics: ``accent_rate`` holds, per dominant terrain code, each place's
    accent count per 100 tiles, and ``accent_size`` the size of every accent. An accent is
    a 4-connected same-terrain patch of a non-dominant terrain inside one place that touches
    no other place. ``transition_width`` holds, per non-barrier border between two places of
    different dominants, the number of depth levels on either side whose mix of the two
    terrains is neither nearly pure one nor the other. ``raw_cut`` holds each map's raw-cut
    length over its total border length.

    The palette statistics: ``palette_counts`` holds one ``PaletteCount`` per level, and
    ``same_by_roles`` maps ``"roleA|roleB"`` with roleA <= roleB to (pairs of adjacent places
    that share a dominant, all adjacent pairs). ``same_by_roles`` is a reading, not a prior
    any step draws from.

    The content statistics: ``content`` holds one ``PlaceContent`` per inferred place of
    a map that has a home. ``roads`` holds the road statistics."""

    counts: tuple[PlaceCount, ...] = ()
    rel_size: Mapping[str, tuple[float, ...]] = field(default_factory=dict[str, tuple[float, ...]])
    adjacency: Mapping[str, int] = field(default_factory=dict[str, int])
    degree: Mapping[str, tuple[int, ...]] = field(default_factory=dict[str, tuple[int, ...]])
    home_separation: tuple[float, ...] = ()
    compactness: Mapping[str, tuple[float, ...]] = field(
        default_factory=dict[str, tuple[float, ...]]
    )
    roughness: Mapping[str, tuple[float, ...]] = field(default_factory=dict[str, tuple[float, ...]])
    dominant: Mapping[str, Mapping[int, int]] = field(default_factory=dict[str, Mapping[int, int]])
    dominant_share: Mapping[str, tuple[float, ...]] = field(
        default_factory=dict[str, tuple[float, ...]]
    )
    border_kinds: Mapping[str, int] = field(default_factory=dict[str, int])
    barrier_depth: tuple[float, ...] = ()
    accent_rate: Mapping[int, tuple[float, ...]] = field(
        default_factory=dict[int, tuple[float, ...]]
    )
    accent_size: Mapping[int, tuple[int, ...]] = field(default_factory=dict[int, tuple[int, ...]])
    transition_width: tuple[int, ...] = ()
    raw_cut: tuple[float, ...] = ()
    palette_counts: tuple[PaletteCount, ...] = ()
    same_by_roles: Mapping[str, tuple[int, int]] = field(default_factory=dict[str, tuple[int, int]])
    content: tuple[PlaceContent, ...] = ()
    roads: RoadStats = field(default_factory=RoadStats)
