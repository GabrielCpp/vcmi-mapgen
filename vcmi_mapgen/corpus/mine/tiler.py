"""Mine the tiler tables: for every corpus tile, the frame and flip real maps draw for its
terrain and its neighbours' terrains. The miner reads tile strings straight from each
``.vmap``, since a loaded ``MapState`` keeps only the terrain."""

import collections
from collections.abc import Iterable, Iterator, Sequence

from vcmi_mapgen.corpus.maps import all_map_names, corpus_path
from vcmi_mapgen.vcmi.formats import vmap as VM
from vcmi_mapgen.vcmi.tiles import (
    SigTable,
    TilerTables,
    ViewMirror,
    decode_tile_string,
    four_of,
    neighbours8,
)

type TileGrid = Sequence[Sequence[str]]


def corpus_tile_grids() -> Iterator[TileGrid]:
    """Every level of every corpus map that reads, as tile strings."""
    for name in all_map_names():
        try:
            doc = VM.read(corpus_path(name))
        except Exception:
            continue
        yield from doc.terrain


def learn(grids: Iterable[TileGrid]) -> TilerTables:
    """Count each tile's frame and flip under its terrain with all eight neighbours, under
    its terrain with the four edge neighbours, and, for a tile whose neighbours all share
    its terrain, under its terrain alone."""
    exact: SigTable = collections.defaultdict(collections.Counter)
    four: SigTable = collections.defaultdict(collections.Counter)
    clean: dict[int, collections.Counter[ViewMirror]] = collections.defaultdict(collections.Counter)
    for grid in grids:
        cells = [[decode_tile_string(s) for s in row] for row in grid]
        ids = [[c.t for c in row] for row in cells]
        for y, row in enumerate(cells):
            for x, c in enumerate(row):
                vm = (c.view, c.m)
                sig = neighbours8(ids, x, y)
                exact[(c.t, sig)][vm] += 1
                four[(c.t, four_of(sig))][vm] += 1
                if all(v == c.t for v in sig):
                    clean[c.t][vm] += 1
    return TilerTables(exact, four, clean)
