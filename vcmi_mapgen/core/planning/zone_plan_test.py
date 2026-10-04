from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.placement.footprint import overlay_cells
from vcmi_mapgen.core.planning.zone_plan import PlanZone, town_room


def _strip(top: int) -> PlanZone:
    """A zone four rows high from row ``top``, its bottom row the web."""
    ts = frozenset((x, y) for x in range(12) for y in range(top, top + 4))
    web = frozenset((x, top + 3) for x in range(12))
    return PlanZone("grass", ts, (), web, frozenset(), frozenset())


def test_a_strict_town_room_needs_the_whole_sprite_inside_the_zone(catalog: Catalog) -> None:
    assert town_room(catalog, _strip(10), set()) is None


def test_a_home_town_room_lets_its_overlay_reach_past_the_zone(catalog: Catalog) -> None:
    zone = _strip(10)
    room = town_room(catalog, zone, set(), 20)
    assert room is not None
    outside = room.cells - zone.ts
    assert outside
    assert room.blk <= zone.ts
    anchor = max(room.blk, key=lambda t: (t[1], t[0]))
    assert outside <= overlay_cells(catalog.random_town().footprint, anchor)


def test_a_home_town_overlay_stays_on_the_map(catalog: Catalog) -> None:
    assert town_room(catalog, _strip(0), set(), 20) is None
