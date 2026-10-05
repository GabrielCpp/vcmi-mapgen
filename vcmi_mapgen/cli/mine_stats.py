from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from vcmi_mapgen.cli.settings import Settings
from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState
from vcmi_mapgen.core.priors.markov import MarkovTables
from vcmi_mapgen.corpus.effort import save_effort, tuned_effort
from vcmi_mapgen.corpus.gameplay import save_gameplay
from vcmi_mapgen.corpus.gates import save_gate_stats
from vcmi_mapgen.corpus.macro import save_macro
from vcmi_mapgen.corpus.maps import named_corpus_maps
from vcmi_mapgen.corpus.markov import save_inside, save_tables
from vcmi_mapgen.corpus.mine.effort import mine_effort
from vcmi_mapgen.corpus.mine.gameplay import mine_gameplay
from vcmi_mapgen.corpus.mine.gates import mine_gate_stats
from vcmi_mapgen.corpus.mine.macro import mine_macro
from vcmi_mapgen.corpus.mine.markov import learn, learn4, learn_inside
from vcmi_mapgen.corpus.mine.places import map_players, mine_places, place_labels
from vcmi_mapgen.corpus.mine.tiler import corpus_tile_grids
from vcmi_mapgen.corpus.mine.tiler import learn as learn_tiler
from vcmi_mapgen.corpus.mine.vegetation import mine as mine_vegetation
from vcmi_mapgen.corpus.places import save_places
from vcmi_mapgen.corpus.tiler import save_tiler
from vcmi_mapgen.corpus.vegetation import save_vegetation

LEVELS = (0, 1)


@dataclass(frozen=True, slots=True)
class MineInput:
    """What every miner reads: the loaded corpus with each map's name, the catalog, and the
    directories the corpus, its ``.h3m`` sources and the mined caches live in."""

    maps: Sequence[MapState]
    names: Sequence[str]
    catalog: Catalog
    pp_dir: Path
    maps_dir: Path
    h3m_dir: Path


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


def _places(m: MineInput) -> None:
    players = [map_players(m.h3m_dir, name) for name in m.names]
    for level in LEVELS:
        save_places(m.pp_dir, level, mine_places(m.catalog, level, m.maps, players))


def _markov_places(m: MineInput) -> None:
    for level in LEVELS:
        labels = place_labels(m.catalog, level, m.maps)
        save_inside(m.pp_dir, level, learn_inside(level, m.maps, labels))


def _effort(m: MineInput) -> None:
    owners = [map_players(m.h3m_dir, name).owners for name in m.names]
    save_effort(m.pp_dir, mine_effort(m.catalog, m.maps, owners, tuned_effort(m.pp_dir)))


MINERS: dict[str, Callable[[MineInput], None]] = {
    "macro": _macro,
    "markov": _markov,
    "tiler": _tiler,
    "gates": _gates,
    "gameplay": _gameplay,
    "vegetation": _vegetation,
    "places": _places,
    "markov_places": _markov_places,
    "effort": _effort,
}


def mine_stats(catalog: Catalog, settings: Settings, only: Sequence[str] = ()) -> None:
    named = named_corpus_maps(settings.maps_dir)
    maps = [m for _, m in named]
    mine_input = MineInput(
        maps,
        [name for name, _ in named],
        catalog,
        settings.pp_dir,
        settings.maps_dir,
        settings.h3m_dir,
    )
    for name, miner in MINERS.items():
        if only and name not in only:
            continue
        print(f"mining {name} over {len(maps)} maps")
        miner(mine_input)
