"""Where each player starts: the visit tiles of every player's starting town."""

from vcmi_mapgen.core.model import MapState, PlacedObject
from vcmi_mapgen.core.reading.routes import Spot


def town_spots(town: PlacedObject) -> list[Spot]:
    """The visit tiles of one town."""
    return [
        Spot(town.level, x, y)
        for (x, y), role in town.footprint.at(town.x, town.y)
        if role.interactive
    ]


def town_homes(map_state: MapState) -> list[list[Spot]]:
    """The visit tiles of each player's starting town, one list per town."""
    return [town_spots(t) for t in map_state.player_towns]
