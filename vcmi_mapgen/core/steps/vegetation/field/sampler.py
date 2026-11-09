"""The field sampler: decorations placed to cover the blocked mask a cellular field draws for
one zone, under the canvas's hard rules."""

from typing import final

from vcmi_mapgen.core.planning.web import ZoneRef
from vcmi_mapgen.core.steps.vegetation.canvas import ZoneCanvas, zone_rng
from vcmi_mapgen.core.steps.vegetation.field.cellular import cellular_field
from vcmi_mapgen.core.steps.vegetation.model import VegModel
from vcmi_mapgen.core.steps.vegetation.planting import Planter, planting_plan
from vcmi_mapgen.core.steps.vegetation.sampler import SampleOptions, ZoneGrowth


@final
class FieldSampler:
    def sample(self, zone: ZoneRef, model: VegModel, seed: int, opts: SampleOptions) -> ZoneGrowth:
        """Cover a cellular field's blocked mask with decorations in one zone, under the
        canvas's hard rules: nothing on `forbid` or the protected web, and no open ground
        walled off. The `border` tiles are part of the mask outright, so the zone front
        outside its entrance bands closes by construction, and the field shapes only the
        interior."""
        if not model.cats:
            return [], set(), set()
        canvas = ZoneCanvas(zone, model, opts)
        rng = zone_rng(zone, seed)
        planter = Planter(canvas, model, rng)
        field = cellular_field(canvas.W, canvas.H, rng)
        return planter.cover(planting_plan(canvas, model, field))
