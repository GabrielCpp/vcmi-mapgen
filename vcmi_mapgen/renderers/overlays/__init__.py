"""Semi-transparent map overlay layers for PngRenderer."""

from vcmi_mapgen.renderers.overlays.base import MapOverlay
from vcmi_mapgen.renderers.overlays.blocking import BlockingOverlay
from vcmi_mapgen.renderers.overlays.grid import GridOverlay
from vcmi_mapgen.renderers.overlays.guard import GuardOverlay
from vcmi_mapgen.renderers.overlays.passage import PassageOverlay
from vcmi_mapgen.renderers.overlays.place import PlaceOverlay
from vcmi_mapgen.renderers.overlays.pocket import PocketOverlay
from vcmi_mapgen.renderers.overlays.tile_type import TileTypeOverlay
from vcmi_mapgen.renderers.overlays.zone import ZoneOverlay

__all__ = [
    "BlockingOverlay",
    "GridOverlay",
    "GuardOverlay",
    "MapOverlay",
    "PassageOverlay",
    "PlaceOverlay",
    "PocketOverlay",
    "TileTypeOverlay",
    "ZoneOverlay",
]
