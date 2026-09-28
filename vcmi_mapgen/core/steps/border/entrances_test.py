"""Reliability tests for the entrance guards BorderStep places."""

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import Footprint, PlacedObject, Role, Tile, Zone
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.placement.guards import guard_spaced
from vcmi_mapgen.core.planning.entrances import plan_entrances
from vcmi_mapgen.core.steps.border.entrances import EntranceField, guard_entrances

GRASS = 2


def _zone(ts: set[Tile], cx: float, cy: float) -> Zone:
    return Zone(
        terrain_type=Terrain(GRASS),
        area=len(ts),
        centroid=(cx, cy),
        tiles=sorted(ts),
        tiles_set=frozenset(ts),
    )


def _field(skip: frozenset[int] | None = None) -> tuple[EntranceField, set[Tile], set[Tile]]:
    ts1 = {(x, y) for x in range(14) for y in range(12)}
    ts2 = {(x, y) for x in range(14, 28) for y in range(12)}
    zones = {1: _zone(ts1, 6.5, 5.5), 2: _zone(ts2, 20.5, 5.5)}
    plan = plan_entrances(zones)
    crossing = {t for zid in plan for r, b, _o in plan[zid] for t in b | {r}}
    field = EntranceField(
        plan=plan,
        zone_tiles={1: frozenset(ts1), 2: frozenset(ts2)},
        home_zids=frozenset[int](),
        skip_zids=skip or frozenset[int](),
        avoid=frozenset[Tile](),
    )
    return field, ts1, crossing


def _hostile(t: Tile) -> PlacedObject:
    return PlacedObject(
        x=t[0],
        y=t[1],
        level=0,
        purpose=Purpose.GUARD,
        type="randomMonsterLevel1",
        subtype="object",
        animation="",
        footprint=Footprint.one(Role.VISIT),
    )


def test_only_the_lower_zone_guards_a_pair_on_its_entrance(catalog: Catalog) -> None:
    """One crossing gets at most one guard, emitted by the lower zone id, standing on the
    planned representative or band tile inside that zone."""
    field, ts1, crossing = _field()
    n_guarded = 0
    for seed in range(1, 7):
        guards = guard_entrances(catalog, field, [], seed, 0)
        assert guards == guard_entrances(catalog, field, [], seed, 0), "deterministic"
        assert all((g.x, g.y) in crossing and (g.x, g.y) in ts1 for g in guards)
        assert len(guards) <= len(field.plan[1])
        n_guarded += len(guards)
    assert n_guarded >= 3, f"most entrances should be guarded, got {n_guarded}/6"


def test_an_entrance_guard_keeps_its_distance_from_an_existing_guard(catalog: Catalog) -> None:
    field, _ts1, crossing = _field()
    near = [_hostile(t) for t in sorted(crossing)]
    for seed in range(1, 7):
        guards = guard_entrances(catalog, field, near, seed, 0)
        assert all(guard_spaced((g.x, g.y), [(o.x, o.y) for o in near]) for g in guards)


def test_a_skipped_zone_gets_no_entrance_guard(catalog: Catalog) -> None:
    field, _ts1, _crossing = _field(skip=frozenset({1}))
    assert all(not guard_entrances(catalog, field, [], seed, 0) for seed in range(1, 7))
