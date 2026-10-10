"""Load every prior one generation run reads, once, into a ``Priors`` value."""

from pathlib import Path

from vcmi_mapgen.core.grid.pocket_masks import parse_masks
from vcmi_mapgen.core.priors.bundle import Priors, TerrainPriors
from vcmi_mapgen.corpus.effort import load_effort
from vcmi_mapgen.corpus.gameplay import load_gameplay
from vcmi_mapgen.corpus.gates import load_gate_stats
from vcmi_mapgen.corpus.macro import load_macro
from vcmi_mapgen.corpus.markov import load_inside, load_tables
from vcmi_mapgen.corpus.mines import load_mines
from vcmi_mapgen.corpus.places import load_places
from vcmi_mapgen.corpus.territories import load_territories
from vcmi_mapgen.corpus.vegetation import load_vegetation, vegetation_terrains
from vcmi_mapgen.corpus.water import load_water

LEVELS = (0, 1)


def load_priors(pp_dir: Path, pockets_file: Path) -> Priors:
    """The terrain, gameplay and place statistics of both levels, the gate estimator, the
    vegetation statistics of every terrain that has them, the effort priors, the water
    priors, the territory spread and the resource mine curve, all read from ``pp_dir``, and
    the pocket masks drawn in ``pockets_file``."""
    return Priors(
        terrain={
            lv: TerrainPriors(
                load_macro(pp_dir, lv), load_tables(pp_dir, lv), load_inside(pp_dir, lv)
            )
            for lv in LEVELS
        },
        gameplay={lv: load_gameplay(pp_dir, lv) for lv in LEVELS},
        gates=load_gate_stats(pp_dir),
        vegetation={t: load_vegetation(pp_dir, t) for t in vegetation_terrains(pp_dir)},
        pocket_masks=parse_masks(pockets_file.read_text()),
        places={lv: load_places(pp_dir, lv) for lv in LEVELS},
        effort=load_effort(pp_dir),
        water=load_water(pp_dir),
        territories=load_territories(pp_dir),
        mines=load_mines(pp_dir),
    )
