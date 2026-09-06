"""FmDocumentStep — a rebuilt/generated faithful-shaped dict -> a writable VmapDocument."""
from __future__ import annotations

from vcmi_mapgen.pipeline import PipelineStep
from vcmi_mapgen.rebuild.engine import fm_to_document


class FmDocumentStep(PipelineStep):
    """Build the final writable VmapDocument from a rebuilt/generated faithful-shaped dict.

    Config:
        name  The document's map name.

    inject(ctx): ``fm`` (RebuildMapStep's or DeformWarpStep's output).

    Produces: ``document`` (a VmapDocument, ready for kit.vmap.writer.write), written
    into ctx.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.document = None
        self._ctx: dict = {}
        self._fm: dict = {}

    def inject(self, ctx: dict) -> None:
        self._ctx = ctx
        self._fm = self._require(ctx, "fm", dict)

    def run(self, ontology, map_state) -> None:
        self.document = fm_to_document(self._fm, name=self.name)
        self._ctx["document"] = self.document
