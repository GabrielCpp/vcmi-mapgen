"""Whether an object stands hemmed in: both flanks of its sprite closed. Hand-made maps hem
about two objects in three. The reader counts hemmed objects the same way on a corpus map and
on a generated one."""

from dataclasses import dataclass

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.grid.flanks import closed_flanks
from vcmi_mapgen.core.model import MapState
from vcmi_mapgen.core.model.purpose import FLANKED
from vcmi_mapgen.core.reading.ground import purpose_of, read_ground


@dataclass(frozen=True, slots=True)
class Hemmed:
    """The flanked objects of a map and how many of them stand hemmed."""

    hemmed: int = 0
    objects: int = 0

    def __add__(self, other: "Hemmed") -> "Hemmed":
        return Hemmed(self.hemmed + other.hemmed, self.objects + other.objects)

    @property
    def share(self) -> float | None:
        return self.hemmed / self.objects if self.objects else None


def read_hemmed(catalog: Catalog, map_state: MapState, level: int) -> Hemmed:
    """The hemmed count of the flanked objects on ``level``."""
    ground = read_ground(catalog, map_state, level)
    if ground is None:
        return Hemmed()
    walk = ground.walk
    out = Hemmed()
    for obj in map_state.objs_by_level([level])[level]:
        if purpose_of(catalog, obj) in FLANKED:
            cells = [t for t, _role in obj.footprint.at(obj.x, obj.y)]
            out += Hemmed(int(closed_flanks(cells, lambda t: t not in walk) == 2), 1)
    return out
