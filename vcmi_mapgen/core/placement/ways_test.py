from vcmi_mapgen.core.model import CoverIndex, Footprint, PlacedObject, Role
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.placement.ways import WayRule, home_ways

_WAY = [(x, 5) for x in range(10)]


def _obj(x: int, y: int, purpose: str, role: Role = Role.BLOCKING) -> PlacedObject:
    fp = Footprint(1, 1, ((0, 0, role),))
    return PlacedObject(x=x, y=y, level=0, purpose=purpose, kind=purpose, footprint=fp)


def _covers() -> CoverIndex:
    return CoverIndex(rules=(WayRule(_WAY),))


def test_a_guard_beside_the_way_is_refused() -> None:
    assert not _covers().accepts(_obj(3, 6, Purpose.GUARD, Role.VISIT))


def test_a_guard_two_tiles_off_the_way_stands() -> None:
    assert _covers().accepts(_obj(3, 7, Purpose.GUARD, Role.VISIT))


def test_a_solid_object_on_the_way_is_refused() -> None:
    assert not _covers().accepts(_obj(4, 5, Purpose.DWELLING))


def test_a_pickup_on_the_way_stands() -> None:
    assert _covers().accepts(_obj(4, 5, Purpose.RESOURCE_PILE, Role.VISIT))


def test_a_kept_way_grows() -> None:
    rule = WayRule()
    covers = CoverIndex(rules=(rule,))
    rule.keep([(1, 1)])
    assert not covers.accepts(_obj(1, 1, Purpose.DWELLING))


def _zones(rows: list[str]) -> dict[tuple[int, int], int]:
    return {(x, y): int(c) for y, row in enumerate(rows) for x, c in enumerate(row) if c != "#"}


def test_a_home_way_leads_to_each_bordering_zone() -> None:
    zones = _zones(["1110", "1#10", "1112"])
    kept = home_ways((0, 0), zones, lambda t: t in zones, lambda _t: False)
    assert {(3, 0), (3, 2)} <= kept
    assert (0, 0) in kept


def test_a_home_way_stops_at_a_threatened_tile() -> None:
    zones = _zones(["11110"])
    kept = home_ways((0, 0), zones, lambda t: t in zones, lambda t: t == (2, 0))
    assert kept == set()


def test_a_home_way_starts_nowhere_from_a_blocked_tile() -> None:
    zones = _zones(["10"])
    assert home_ways((0, 0), zones, lambda _t: False, lambda _t: False) == set()
