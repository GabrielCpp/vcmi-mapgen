from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from vcmi_mapgen.cli.settings import Settings
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


@dataclass(frozen=True, slots=True)
class MineInput:
    """What every miner reads: the loaded corpus, the catalog, and the directories the corpus
    and the mined caches live in."""

    maps: Sequence[MapState]
    catalog: Catalog
    pp_dir: Path
    maps_dir: Path


def _macro(m: MineInput) -> None:
    for level in LEVELS:
        save_macro(m.pp_dir, level, mine_macro(level, m.maps))


def _markov(m: MineInput) -> None:
    for level in LEVELS:
        tables = MarkovTables(chain=learn(level, m.maps), chain4=learn4(level, m.maps))
        save_tables(m.pp_dir, level, tables)


def _tiler(m: MineInput) -> None:
    save_tiler(m.pp_dir, learn_tiler(corpus_tile_grids(m.maps_dir)))


def _gates(m: MineInput) -> None:
    save_gate_stats(m.pp_dir, mine_gate_stats(m.maps))


def _gameplay(m: MineInput) -> None:
    for level in LEVELS:
        save_gameplay(m.pp_dir, level, mine_gameplay(m.catalog, level, m.maps))


def _vegetation(m: MineInput) -> None:
    save_vegetation(m.pp_dir, mine_vegetation(m.catalog, m.maps))


MINERS: dict[str, Callable[[MineInput], None]] = {
    "macro": _macro,
    "markov": _markov,
    "tiler": _tiler,
    "gates": _gates,
    "gameplay": _gameplay,
    "vegetation": _vegetation,
}


def mine_stats(catalog: Catalog, settings: Settings, only: Sequence[str] = ()) -> None:
    maps = corpus_maps(settings.maps_dir)
    mine_input = MineInput(maps, catalog, settings.pp_dir, settings.maps_dir)
    for name, miner in MINERS.items():
        if only and name not in only:
            continue
        print(f"mining {name} over {len(maps)} maps")
        miner(mine_input)
