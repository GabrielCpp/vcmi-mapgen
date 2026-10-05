"""How many towns-aside gameplay objects sit snug for their size. Hand-made maps tuck four
one-tile objects in five into a hole or a corner, three two-tile objects in four against a
closed tile past their far end, and nine larger objects in ten with their top against one. The
reader counts the same way on a corpus map and on a generated one."""

from collections import Counter
from dataclasses import dataclass, field

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.grid.snug import size_class, snug
from vcmi_mapgen.core.model import MapState
from vcmi_mapgen.core.model.purpose import FLANKED, Purpose
from vcmi_mapgen.core.reading.ground import purpose_of, read_ground


@dataclass(frozen=True, slots=True)
class Snug:
    """Per size class, the gameplay objects and how many of them sit snug."""

    snug: Counter[int] = field(default_factory=Counter[int])
    objects: Counter[int] = field(default_factory=Counter[int])

    def __add__(self, other: "Snug") -> "Snug":
        return Snug(self.snug + other.snug, self.objects + other.objects)

    def share(self, size: int) -> float | None:
        n = self.objects[size]
        return self.snug[size] / n if n else None


def read_snug(catalog: Catalog, map_state: MapState, level: int) -> Snug:
    """The snug count by size class of the gameplay objects on ``level``, towns left out."""
    ground = read_ground(catalog, map_state, level)
    out = Snug()
    if ground is None:
        return out
    walk = ground.walk
    for obj in map_state.objs_by_level([level])[level]:
        purpose = purpose_of(catalog, obj)
        if purpose not in FLANKED or purpose == Purpose.TOWN:
            continue
        size = size_class(obj.footprint)
        out.objects[size] += 1
        out.snug[size] += snug(obj.footprint, (obj.x, obj.y), lambda t: t not in walk)
    return out
