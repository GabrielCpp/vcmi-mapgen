"""The corpus priors one generation run reads, which ``cli`` loads once and hands to the
step constructors."""

from collections.abc import Mapping
from dataclasses import dataclass

from vcmi_mapgen.core.priors.gameplay import GameplayStats
from vcmi_mapgen.core.priors.gates import GateStats
from vcmi_mapgen.core.priors.macro import MacroStats
from vcmi_mapgen.core.priors.markov import MarkovTables
from vcmi_mapgen.core.priors.vegetation import VegetationStats


@dataclass(frozen=True, slots=True)
class TerrainPriors:
    """One terrain level's macro statistics and the Markov tables that texture its zone
    borders."""

    macro: MacroStats
    markov: MarkovTables


@dataclass(frozen=True, slots=True)
class Priors:
    """Every prior a run reads: terrain and gameplay statistics per level (0 = surface,
    1 = underground), the gate estimator, and the vegetation statistics per terrain name."""

    terrain: Mapping[int, TerrainPriors]
    gameplay: Mapping[int, GameplayStats]
    gates: GateStats
    vegetation: Mapping[str, VegetationStats]
