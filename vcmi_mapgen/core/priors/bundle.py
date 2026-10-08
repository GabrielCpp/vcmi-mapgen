"""The corpus priors one generation run reads, which ``cli`` loads once and hands to the
step constructors."""

from collections.abc import Mapping
from dataclasses import dataclass, field

from vcmi_mapgen.core.priors.effort import EffortPriors
from vcmi_mapgen.core.priors.gameplay import GameplayStats
from vcmi_mapgen.core.priors.gates import GateStats
from vcmi_mapgen.core.priors.macro import MacroStats
from vcmi_mapgen.core.priors.markov import MarkovTables, empty_tables
from vcmi_mapgen.core.priors.places import PlaceStats
from vcmi_mapgen.core.priors.pocket_masks import PocketMask
from vcmi_mapgen.core.priors.territories import TerritoryStats
from vcmi_mapgen.core.priors.vegetation import VegetationStats
from vcmi_mapgen.core.priors.water import WaterPriors


@dataclass(frozen=True, slots=True)
class TerrainPriors:
    """One terrain level's macro statistics, the Markov tables that texture its zone
    borders, and the tables counted inside inferred places that texture each place."""

    macro: MacroStats
    markov: MarkovTables
    markov_places: MarkovTables = field(default_factory=empty_tables)


@dataclass(frozen=True, slots=True)
class Priors:
    """Every prior a run reads: terrain, gameplay and place statistics per level (0 = surface,
    1 = underground), the gate estimator, the vegetation statistics per terrain name, every
    orientation of the drawn pocket masks, the guard toll and effort bands, the fitted odds
    of surface water with the corpus water targets, and the territory spread per level."""

    terrain: Mapping[int, TerrainPriors]
    gameplay: Mapping[int, GameplayStats]
    gates: GateStats
    vegetation: Mapping[str, VegetationStats]
    pocket_masks: tuple[PocketMask, ...]
    places: Mapping[int, PlaceStats]
    effort: EffortPriors = field(default_factory=EffortPriors)
    water: WaterPriors = field(default_factory=WaterPriors)
    territories: Mapping[int, TerritoryStats] = field(default_factory=dict[int, TerritoryStats])
