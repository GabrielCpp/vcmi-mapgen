"""RebuildMapStep — template + target terrain -> replayed objects (bit-exact on the
source shape; a missing-zone count on any other target shape)."""
from __future__ import annotations

from vcmi_mapgen.pipeline import PipelineStep
from vcmi_mapgen.rebuild.engine import rebuild_map


class RebuildMapStep(PipelineStep):
    """Replay a zone template onto target terrain.

    Config:
        identity  Whether the target terrain is the source's own (enables the
                   bit-exact integer replay path).

    inject(ctx): ``template`` (ExtractTemplateStep's output), ``target_terrain`` (the
    target map's terrain grids — the source faithful map's own for an identity
    rebuild; seeded into ctx by the caller before running, since it isn't any step's
    own output).

    Produces: ``fm`` (the rebuilt faithful-shaped dict), ``stats`` (zones matched/
    missing) — both written into ctx.
    """

    def __init__(self, identity: bool = True) -> None:
        self.identity = identity
        self.fm: dict = {}
        self.stats: dict = {}
        self._ctx: dict = {}
        self._template: dict = {}
        self._target_terrain: list = []

    def inject(self, ctx: dict) -> None:
        self._ctx = ctx
        self._template = self._require(ctx, "template", dict)
        self._target_terrain = self._require(ctx, "target_terrain", list)

    def run(self, ontology, map_state) -> None:
        self.fm, self.stats = rebuild_map(self._template, self._target_terrain,
                                          identity=self.identity)
        self._ctx["fm"] = self.fm
        self._ctx["stats"] = self.stats
