from collections.abc import Callable, Sequence

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState
from vcmi_mapgen.core.priors.markov import MarkovTables
from vcmi_mapgen.corpus.gameplay import save_gameplay
from vcmi_mapgen.corpus.gates import save_gate_stats
from vcmi_mapgen.corpus.macro import save_macro
from vcmi_mapgen.corpus.maps import corpus_maps
from vcmi_mapgen.corpus.markov import save_tables
from vcmi_mapgen.corpus.mine.gameplay import mine_gameplay
from vcmi_mapgen.corpus.mine.gates import mine_gate_stats
from vcmi_mapgen.corpus.mine.macro import mine_macro
from vcmi_mapgen.corpus.mine.markov import learn, learn4
from vcmi_mapgen.corpus.mine.tiler import corpus_tile_grids
from vcmi_mapgen.corpus.mine.tiler import learn as learn_tiler
from vcmi_mapgen.corpus.mine.vegetation import mine as mine_vegetation
from vcmi_mapgen.corpus.tiler import save_tiler
from vcmi_mapgen.corpus.vegetation import save_vegetation

LEVELS = (0, 1)


def _macro(maps: Sequence[MapState], _catalog: Catalog) -> None:
    for level in LEVELS:
        save_macro(level, mine_macro(level, maps))


def _markov(maps: Sequence[MapState], _catalog: Catalog) -> None:
    for level in LEVELS:
        tables = MarkovTables(chain=learn(level, maps), chain4=learn4(level, maps))
        save_tables(level, tables)


def _tiler(_maps: Sequence[MapState], _catalog: Catalog) -> None:
    save_tiler(learn_tiler(corpus_tile_grids()))


def _gates(maps: Sequence[MapState], _catalog: Catalog) -> None:
    save_gate_stats(mine_gate_stats(maps))


def _gameplay(maps: Sequence[MapState], catalog: Catalog) -> None:
    for level in LEVELS:
        save_gameplay(level, mine_gameplay(catalog, level, maps))


def _vegetation(maps: Sequence[MapState], catalog: Catalog) -> None:
    save_vegetation(mine_vegetation(catalog, maps))


MINERS: dict[str, Callable[[Sequence[MapState], Catalog], None]] = {
    "macro": _macro,
    "markov": _markov,
    "tiler": _tiler,
    "gates": _gates,
    "gameplay": _gameplay,
    "vegetation": _vegetation,
}


def mine_stats(catalog: Catalog, only: Sequence[str] = ()) -> None:
    maps = corpus_maps()
    for name, miner in MINERS.items():
        if only and name not in only:
            continue
        print(f"mining {name} over {len(maps)} maps")
        miner(maps, catalog)
