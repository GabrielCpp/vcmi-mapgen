"""The shapes-first territory front: the place shapes grow on the land first, the homes
stand on them, and the places group into territories."""

from vcmi_mapgen.core.priors.places import PlaceStats
from vcmi_mapgen.core.priors.territories import TerritoryStats
from vcmi_mapgen.core.steps.terrain_gen.coastline import target_gap
from vcmi_mapgen.core.steps.terrain_gen.homes import choose_homes
from vcmi_mapgen.core.steps.terrain_gen.layout import Land
from vcmi_mapgen.core.steps.terrain_gen.model import FrontDraw, TerrainOptions
from vcmi_mapgen.core.steps.terrain_gen.place_map import label_adjacency
from vcmi_mapgen.core.steps.terrain_gen.places import (
    draw_territories,
    land_count,
    land_count_of,
    territory_record,
)
from vcmi_mapgen.core.steps.terrain_gen.shapes import grow_shapes, shape_caps
from vcmi_mapgen.core.steps.terrain_gen.streams import stream
from vcmi_mapgen.core.steps.terrain_gen.territories import home_budget, settle


class ShapesFirst:
    """Shapes, then homes, then territories: the places grow on the land to a corpus size
    mix, the homes are chosen among them, and the places group into as many territories
    as one corpus map near the player count and land holds."""

    def draw(
        self,
        land: Land,
        priors: tuple[PlaceStats, TerritoryStats],
        planned: int,
        seed: int,
        options: TerrainOptions,
    ) -> FrontDraw:
        stats, spread = priors
        caps = shape_caps(
            stats, options.players, (planned, land_count_of(land)), stream(seed, "places")
        )
        layout = grow_shapes(land, caps, stream(seed, "layout"))
        record = territory_record(spread, options.players, planned, seed)
        budget = home_budget(record, land_count(layout.label))
        homes = choose_homes(
            layout, options.players, (target_gap(stats), budget), stream(seed, "homes")
        )
        owners: list[int | None] = [None] * layout.places
        for player, home in enumerate(homes.places):
            owners[home] = player
        grown = label_adjacency(layout.label)
        drawn = draw_territories(owners, (layout.label, grown), record, seed)
        territory, _ = settle(drawn, owners, grown)
        return FrontDraw(layout, homes, territory, owners, record, len(caps))
