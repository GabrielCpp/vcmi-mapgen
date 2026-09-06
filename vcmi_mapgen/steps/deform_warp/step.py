"""DeformWarpStep — rough different-shape warp of one template zone onto a deformed
target (``rebuild --zone N --deform``)."""
from __future__ import annotations

import sys

from vcmi_mapgen.kit import objects as OR
from vcmi_mapgen.kit import terrain_segment as TS
from vcmi_mapgen.kit.segmentation import _segment_level
from vcmi_mapgen.pipeline import PipelineStep
from vcmi_mapgen.rebuild.engine import deform_terrain_level, rebuild_zone_warp


class DeformWarpStep(PipelineStep):
    """Build a deformed single-level map and warp one zone's recorded pattern onto it.

    Config:
        name     Source map name (loaded from the corpus for its terrain/zone shape).
        zone_id  The template zone to warp.

    inject(template): ``template`` (ExtractTemplateStep's output).

    Produces: ``fm`` (a single-level faithful-shaped dict: the deformed terrain +
    the warped zone's objects).
    """

    def __init__(self, name: str, zone_id: int) -> None:
        self.name = name
        self.zone_id = zone_id
        self.fm: dict = {}
        self._template: dict = {}

    def inject(self, *, template: dict) -> None:
        self._template = template

    def run(self) -> None:
        src = OR.load_faithful(self.name)
        W, H = src["width"], src["height"]
        zones0, _label0 = TS.segment(src["terrain"][0])
        if self.zone_id not in zones0:
            sys.exit(f"zone {self.zone_id} not on level 0 (have {sorted(zones0)})")
        ztmpl = next(z for z in self._template["levels"][0]["zones"]
                     if z["zone_id"] == self.zone_id)
        grid = deform_terrain_level(zones0[self.zone_id], W, H)
        zones_d, _label_d, canon_d = _segment_level(grid)
        if not zones_d:
            sys.exit("deformed terrain produced no zone")
        tzid = max(zones_d, key=lambda z: zones_d[z]["area"])
        placed, info = rebuild_zone_warp(ztmpl, zones_d[tzid], canon_d[tzid], 0)
        print(f"deform warp zone {self.zone_id} ({ztmpl['label']}): src={info['src']} "
              f"placed={info['placed']} dropped={info['dropped']}")
        self.fm = {"name": f"Deform-{self.name}", "width": W, "height": H,
                   "twoLevel": False, "players": 1, "terrain": [grid], "objects": placed}
