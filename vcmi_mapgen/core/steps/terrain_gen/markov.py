"""The markov terrain model: the macro zone growth on every level, despeckled, with one
middle place per same-terrain region."""

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.steps.terrain_gen import macro as MTOPO
from vcmi_mapgen.core.steps.terrain_gen.despeckle import despeckle
from vcmi_mapgen.core.steps.terrain_gen.levels import level_protect, raw_levels
from vcmi_mapgen.core.steps.terrain_gen.model import TerrainDraw, TerrainOptions
from vcmi_mapgen.core.steps.terrain_gen.place_map import flood_places
from vcmi_mapgen.core.steps.terrain_gen.result import PlaceMap


class MarkovTerrain:
    """Today's generator: ``raw_levels`` then despeckle, level by level."""

    def draw(
        self, catalog: Catalog, priors: Priors, seed: int, options: TerrainOptions
    ) -> TerrainDraw:
        raw = raw_levels(
            priors.terrain,
            options.size,
            seed,
            MTOPO.MacroOptions(water_mode=options.water_mode, level=0),
            options.subterrain,
        )
        thin = catalog.thin_terrains()
        grids = {
            level: despeckle(grid, thin, level_protect(level, raw.tunnel_protect))
            for level, grid in raw.grids.items()
        }
        places = PlaceMap({level: flood_places(grid) for level, grid in grids.items()})
        return TerrainDraw(grids, raw.tunnel_protect, places)
