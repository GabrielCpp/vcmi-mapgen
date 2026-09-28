from collections.abc import Callable, Sequence

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState
from vcmi_mapgen.core.steps.gameplay import mines
from vcmi_mapgen.core.steps.gate import gates
from vcmi_mapgen.core.steps.terrain_gen import macro_topo, markov
from vcmi_mapgen.core.steps.vegetation import stats as veg_stats
from vcmi_mapgen.corpus.maps import corpus_maps
from vcmi_mapgen.kit import tiling

LEVELS = (0, 1)


def _macro(maps: Sequence[MapState], _catalog: Catalog) -> None:
    for level in LEVELS:
        macro_topo.save_macro(level, macro_topo.mine_macro(level, maps))


def _markov(maps: Sequence[MapState], _catalog: Catalog) -> None:
    for level in LEVELS:
        tables = markov.MarkovTables(
            chain=markov.learn(level, maps), chain4=markov.learn4(level, maps)
        )
        markov.save_tables(level, tables)


def _tiler(maps: Sequence[MapState], _catalog: Catalog) -> None:
    tiling.save_tiler(tiling.learn_terrain_tiler(maps))


def _gates(maps: Sequence[MapState], _catalog: Catalog) -> None:
    gates.save_gate_stats(gates.mine_gate_stats(maps))


def _gameplay(maps: Sequence[MapState], catalog: Catalog) -> None:
    for level in LEVELS:
        mines.save_gameplay(level, mines.mine_gameplay(catalog, level, maps))


def _vegetation(maps: Sequence[MapState], catalog: Catalog) -> None:
    veg_stats.save(veg_stats.mine(catalog, maps))


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
