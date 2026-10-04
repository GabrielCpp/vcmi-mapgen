"""The place map of a terrain grid: the places a same-terrain flood fill reads, the
adjacency a label grid realises, and the repair that keeps every place one terrain and one
piece once despeckle and the gate sites have changed the grid under it."""

import collections
from collections.abc import Mapping, Sequence

from vcmi_mapgen.core.grid.components import components
from vcmi_mapgen.core.grid.reach import STEPS4
from vcmi_mapgen.core.grid.segment import ZoneLabel, flood_label
from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.planning.entrances import ENTRANCE_W, all_passages
from vcmi_mapgen.core.reading.borders import AdjacencyKind
from vcmi_mapgen.core.reading.places import PlaceRole
from vcmi_mapgen.core.steps.terrain_gen.result import LevelPlaces, PlannedPlace

type Grid = Sequence[Sequence[Terrain]]


def label_adjacency(label: ZoneLabel) -> frozenset[tuple[int, int]]:
    """Every pair ``(a, b)``, ``a < b``, of labels that touch across a tile edge."""
    H, W = len(label), len(label[0])
    pairs: set[tuple[int, int]] = set()
    for y in range(H):
        for x in range(W):
            a = label[y][x]
            if a < 0:
                continue
            for nx, ny in ((x + 1, y), (x, y + 1)):
                if nx < W and ny < H and label[ny][nx] >= 0 and label[ny][nx] != a:
                    b = label[ny][nx]
                    pairs.add((min(a, b), max(a, b)))
    return frozenset(pairs)


def front_cells(label: ZoneLabel) -> frozenset[Tile]:
    """Every labelled tile with an 8-neighbour of another label."""
    H, W = len(label), len(label[0])
    return frozenset(
        (x, y)
        for y in range(H)
        for x in range(W)
        if label[y][x] >= 0
        and any(
            0 <= x + dx < W and 0 <= y + dy < H and label[y + dy][x + dx] not in (-1, label[y][x])
            for dx in (-1, 0, 1)
            for dy in (-1, 0, 1)
        )
    )


def flood_places(grid: Grid, entrance_w: int = ENTRANCE_W) -> LevelPlaces:
    """One middle place with no owner per same-terrain region, with the adjacency it
    realises, every pair of it gated and given the passages ``plan_entrances`` plans with
    bands ``entrance_w`` front tiles wide."""
    label = flood_label(grid)
    places: dict[int, PlannedPlace] = {}
    for y, row in enumerate(label):
        for x, z in enumerate(row):
            if z >= 0 and z not in places:
                places[z] = PlannedPlace(PlaceRole.MIDDLE, None, Terrain(grid[y][x]))
    adjacency = label_adjacency(label)
    kinds = dict.fromkeys(sorted(adjacency), AdjacencyKind.GATED)
    return LevelPlaces(
        label, places, adjacency, kinds=kinds, passages=all_passages(label, entrance_w)
    )


def _mismatched(grid: Grid, label: list[list[int]], places: Mapping[int, PlannedPlace]) -> bool:
    return any(
        Terrain(t).is_land and (z < 0 or places[z].dominant != t)
        for row_t, row_z in zip(grid, label, strict=True)
        for t, z in zip(row_t, row_z, strict=True)
    )


def _follow_terrain(grid: Grid, label: list[list[int]], places: Mapping[int, PlannedPlace]) -> None:
    """Hand each land tile whose terrain differs from its place's to the neighbouring place
    of that terrain it touches most, until no tile moves."""
    H, W = len(grid), len(grid[0])
    changed = True
    while changed:
        changed = False
        for y in range(H):
            for x in range(W):
                t = grid[y][x]
                z = label[y][x]
                if not Terrain(t).is_land or (z >= 0 and places[z].dominant == t):
                    continue
                votes = collections.Counter(
                    label[y + dy][x + dx]
                    for dx, dy in STEPS4
                    if 0 <= x + dx < W
                    and 0 <= y + dy < H
                    and grid[y + dy][x + dx] == t
                    and label[y + dy][x + dx] >= 0
                    and places[label[y + dy][x + dx]].dominant == t
                )
                if votes:
                    label[y][x] = min(votes, key=lambda k: (-votes[k], k))
                    changed = True


def _orphans(grid: Grid, label: list[list[int]], places: dict[int, PlannedPlace]) -> None:
    """Each region of land tiles no place of their terrain can take becomes a pocket."""
    H, W = len(grid), len(grid[0])
    loose = {
        (x, y)
        for y in range(H)
        for x in range(W)
        if Terrain(grid[y][x]).is_land
        and (label[y][x] < 0 or places[label[y][x]].dominant != grid[y][x])
    }
    by_terrain: dict[Terrain, set[Tile]] = collections.defaultdict(set)
    for x, y in loose:
        by_terrain[Terrain(grid[y][x])].add((x, y))
    for t in sorted(by_terrain):
        pieces: dict[int, list[Tile]] = collections.defaultdict(list)
        for tile, c in components(by_terrain[t]).items():
            pieces[c].append(tile)
        for c in sorted(pieces):
            pid = max(places, default=-1) + 1
            places[pid] = PlannedPlace(PlaceRole.POCKET, None, t)
            for x, y in pieces[c]:
                label[y][x] = pid


def _tiles_of(label: list[list[int]]) -> dict[int, set[Tile]]:
    out: dict[int, set[Tile]] = collections.defaultdict(set)
    for y, row in enumerate(label):
        for x, z in enumerate(row):
            if z >= 0:
                out[z].add((x, y))
    return out


def _piece_home(
    piece: Sequence[Tile], label: list[list[int]], places: Mapping[int, PlannedPlace], own: int
) -> int | None:
    H, W = len(label), len(label[0])
    votes = collections.Counter(
        label[y + dy][x + dx]
        for x, y in piece
        for dx, dy in STEPS4
        if 0 <= x + dx < W
        and 0 <= y + dy < H
        and label[y + dy][x + dx] not in (-1, own)
        and places[label[y + dy][x + dx]].dominant == places[own].dominant
    )
    return min(votes, key=lambda k: (-votes[k], k)) if votes else None


def _split_pieces(label: list[list[int]], places: dict[int, PlannedPlace]) -> None:
    """Keep each place's largest piece. Every other piece joins a touching place of the
    same terrain, or becomes a pocket of its own."""
    for pid, tiles in sorted(_tiles_of(label).items()):
        pieces: dict[int, list[Tile]] = collections.defaultdict(list)
        for tile, c in components(tiles).items():
            pieces[c].append(tile)
        if len(pieces) < 2:
            continue
        keep = max(pieces, key=lambda c: (len(pieces[c]), -c))
        for c in sorted(pieces):
            if c == keep:
                continue
            target = _piece_home(pieces[c], label, places, pid)
            if target is None:
                target = max(places) + 1
                places[target] = PlannedPlace(PlaceRole.POCKET, None, places[pid].dominant)
            for x, y in pieces[c]:
                label[y][x] = target


def _renumber(
    label: list[list[int]], places: Mapping[int, PlannedPlace], planned: frozenset[tuple[int, int]]
) -> LevelPlaces:
    alive = sorted(_tiles_of(label))
    new = {old: i for i, old in enumerate(alive)}
    grid = [[new[z] if z >= 0 else -1 for z in row] for row in label]
    adjacency = frozenset(
        (min(new[a], new[b]), max(new[a], new[b])) for a, b in planned if a in new and b in new
    )
    return LevelPlaces(grid, {new[p]: places[p] for p in alive}, adjacency)


def reconcile_places(grid: Grid, plan: LevelPlaces) -> LevelPlaces:
    """The place map ``plan`` once the terrain under it became ``grid``. Barrier tiles leave
    their place. A land tile whose terrain differs from its place's moves to a touching
    place of its terrain, or with its region becomes a pocket. Each place keeps one piece.
    Places come out numbered from 0 in their old order."""
    places = dict(plan.places)
    label = [
        [z if Terrain(t).is_land else -1 for t, z in zip(row_t, row_z, strict=True)]
        for row_t, row_z in zip(grid, plan.label, strict=True)
    ]
    if _mismatched(grid, label, places):
        _follow_terrain(grid, label, places)
        _orphans(grid, label, places)
    _split_pieces(label, places)
    return _renumber(label, places, plan.adjacency)
