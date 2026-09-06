"""FmDocumentStep — a rebuilt/generated faithful-shaped dict -> a writable VmapDocument."""
from __future__ import annotations

from vcmi_mapgen.pipeline import PipelineStep
from vcmi_mapgen.rebuild.engine import fm_to_document


class FmDocumentStep(PipelineStep):
    """Build the final writable VmapDocument from a rebuilt/generated faithful-shaped dict.

    Config:
        name  The document's map name.

    inject(fm): ``fm`` (RebuildMapStep's or DeformWarpStep's output).

    Produces: ``document`` (a VmapDocument, ready for kit.vmap.writer.write).
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.document = None
        self._fm: dict = {}

    def inject(self, *, fm: dict) -> None:
        self._fm = fm

    def run(self) -> None:
        self.document = fm_to_document(self._fm, name=self.name)
