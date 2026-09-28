from collections.abc import Callable, Sequence

from vcmi_mapgen.kit import objects as OR
from vcmi_mapgen.kit import tiling
from vcmi_mapgen.steps.gameplay import mines
from vcmi_mapgen.steps.gate import gates
from vcmi_mapgen.steps.terrain_gen import macro_topo, markov
from vcmi_mapgen.steps.vegetation import stats as veg_stats

LEVELS = (0, 1)


def _macro(maps: Sequence[OR.FaithfulMap]) -> None:
    for level in LEVELS:
        macro_topo.save_macro(level, macro_topo.mine_macro(level, maps))


def _markov(maps: Sequence[OR.FaithfulMap]) -> None:
    for level in LEVELS:
        tables = markov.MarkovTables(
            chain=markov.learn(level, maps), chain4=markov.learn4(level, maps)
        )
        markov.save_tables(level, tables)


def _tiler(maps: Sequence[OR.FaithfulMap]) -> None:
    tiling.save_tiler(tiling.learn_terrain_tiler(maps))


def _gates(maps: Sequence[OR.FaithfulMap]) -> None:
    gates.save_gate_stats(gates.mine_gate_stats(maps))


def _gameplay(maps: Sequence[OR.FaithfulMap]) -> None:
    for level in LEVELS:
        mines.save_gameplay(level, mines.mine_gameplay(level, maps))


def _vegetation(maps: Sequence[OR.FaithfulMap]) -> None:
    veg_stats.save(veg_stats.mine(maps))


MINERS: dict[str, Callable[[Sequence[OR.FaithfulMap]], None]] = {
    "macro": _macro,
    "markov": _markov,
    "tiler": _tiler,
    "gates": _gates,
    "gameplay": _gameplay,
    "vegetation": _vegetation,
}


def mine_stats(only: Sequence[str] = ()) -> None:
    maps = OR.corpus_maps()
    for name, miner in MINERS.items():
        if only and name not in only:
            continue
        print(f"mining {name} over {len(maps)} maps")
        miner(maps)
