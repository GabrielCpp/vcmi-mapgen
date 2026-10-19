from typing import final

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import Identity, PlacedObject, Tile, Zone
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.placement import footprint as FP
from vcmi_mapgen.core.steps.vegetation.border_plan import BorderPlan, seal_borders


def _zone(ts: set[Tile]) -> Zone:
    return Zone(
        terrain_type=Terrain.GRASS,
        area=len(ts),
        centroid=(0.0, 0.0),
        tiles=sorted(ts),
        tiles_set=frozenset(ts),
    )


def test_the_sealer_never_shuts_a_piece_of_the_web_away(catalog: Catalog) -> None:
    west = {(x, y) for x in range(4) for y in range(3)} - {(2, 0)}
    east = {(x, y) for x in range(4, 8) for y in range(3)} - {(4, 0)}
    web = {(0, 0), (0, 1), (0, 2), (3, 0), (7, 0), (7, 1), (7, 2)}
    plan = BorderPlan(
        land=west | east,
        zones={1: _zone(west), 2: _zone(east)},
        bands=frozenset[Tile](),
        avoid=web | {(4, y) for y in range(3)},
        web=web,
    )
    _objs, sealed = seal_borders(catalog, plan, [], 1, 0)
    assert (3, 1) not in sealed


def test_the_sealer_never_shuts_the_next_zones_land_away(catalog: Catalog) -> None:
    west = {(x, y) for x in range(4) for y in range(3)}
    east = {(4, 1)}
    web = {(x, 1) for x in range(5)}
    plan = BorderPlan(
        land=west | east,
        zones={1: _zone(west), 2: _zone(east)},
        bands=frozenset[Tile](),
        avoid=web - {(3, 1)},
        web=web,
    )
    _objs, sealed = seal_borders(catalog, plan, [], 1, 0)
    assert (3, 1) not in sealed


def test_the_sealer_thickens_a_wall_to_its_depth(catalog: Catalog) -> None:
    west = {(x, y) for x in range(4) for y in range(5)}
    middle = {(x, y) for x in range(4, 6) for y in range(5)}
    east = {(x, y) for x in range(6, 10) for y in range(5)}
    web = {(0, 2), (9, 2)}
    plan = BorderPlan(
        land=west | middle | east,
        zones={1: _zone(west), 2: _zone(east), 3: _zone(middle)},
        bands=frozenset[Tile](),
        avoid=web,
        web=web,
        open_pairs=frozenset({(1, 3), (2, 3)}),
        depths={(1, 2): 3},
    )
    _objs, sealed = seal_borders(catalog, plan, [], 1, 0)
    near = [
        (a, b)
        for a in west - sealed
        for b in east - sealed
        if max(abs(a[0] - b[0]), abs(a[1] - b[1])) <= 3
    ]
    assert sealed
    assert near == []


@final
class _SinglesOnly:
    def __init__(self, catalog: Catalog) -> None:
        self._catalog = catalog

    def decor(
        self, terrain: str | int, *, blocking: bool | None = None, max_cells: int | None = None
    ) -> list[Identity]:
        _ = max_cells
        return self._catalog.decor(terrain, blocking=blocking, max_cells=1)

    def __getattr__(self, name: str) -> object:
        attr: object = getattr(self._catalog, name)  # pyright: ignore[reportAny]
        return attr


def _two_zones() -> tuple[set[Tile], set[Tile], BorderPlan]:
    west = {(x, y) for x in range(4) for y in range(3)}
    east = {(x, y) for x in range(4, 8) for y in range(3)}
    plan = BorderPlan(
        land=west | east,
        zones={1: _zone(west), 2: _zone(east)},
        bands=frozenset[Tile](),
        avoid=frozenset[Tile](),
        web=frozenset[Tile](),
    )
    return west, east, plan


def _blockers(catalog: Catalog, tiles: list[Tile]) -> list[PlacedObject]:
    one = catalog.decor("grass", blocking=True, max_cells=1)[0]
    return [PlacedObject.at(one, t, level=0, purpose="") for t in tiles]


def _size(o: PlacedObject) -> int:
    return len(FP.cell_offsets(o.footprint)[1])


def test_a_seal_tile_beside_a_blocked_tile_takes_a_two_cell_piece(catalog: Catalog) -> None:
    _west, _east, plan = _two_zones()
    objs = _blockers(catalog, [(5, 0), (5, 1), (5, 2)])
    new, sealed = seal_borders(catalog, plan, objs, 1, 0)
    blocked = FP.blocking_cells(objs)
    larger = [o for o in new if _size(o) > 1]
    assert larger
    assert all(
        c in sealed or c in blocked
        for o in larger
        for c in FP.footprint_cells(o.footprint, o.x, o.y)[1]
    )
    assert any(c in blocked for o in larger for c in FP.footprint_cells(o.footprint, o.x, o.y)[1])


def test_a_seal_tile_with_no_blocked_neighbour_takes_a_single_piece(catalog: Catalog) -> None:
    _west, _east, plan = _two_zones()
    new, sealed = seal_borders(catalog, plan, _blockers(catalog, [(2, 0)]), 1, 0)
    assert sealed
    assert all(_size(o) == 1 for o in new)


def test_larger_pieces_seal_the_same_tiles_as_single_pieces(catalog: Catalog) -> None:
    _west, _east, plan = _two_zones()
    objs = _blockers(catalog, [(2, 0), (2, 1), (2, 2)])
    _new, sealed = seal_borders(catalog, plan, objs, 1, 0)
    _single, base = seal_borders(_SinglesOnly(catalog), plan, objs, 1, 0)  # pyright: ignore[reportArgumentType]
    assert sealed == base
