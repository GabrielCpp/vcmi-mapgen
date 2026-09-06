"""VerifyStep — multiset-compare a rebuilt map's objects to its source (the bit-exact
identity guarantee's check)."""
from __future__ import annotations

from vcmi_mapgen.pipeline import PipelineStep
from vcmi_mapgen.rebuild.engine import verify_identity


class VerifyStep(PipelineStep):
    """Verify a rebuilt map is bit-exact identical to its source.

    Config:
        name  Source map name (loaded from the corpus for comparison).

    inject(ctx): ``fm`` (RebuildMapStep's output).

    Produces (into ctx): ``verify`` — the ``(ok, total, matched, missing, extra)`` tuple.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.ok: bool = False
        self.total: int = 0
        self.matched: int = 0
        self.missing = None
        self.extra = None
        self._ctx: dict = {}
        self._fm: dict = {}

    def inject(self, ctx: dict) -> None:
        self._ctx = ctx
        self._fm = self._require(ctx, "fm", dict)

    def run(self, ontology, map_state) -> None:
        self.ok, self.total, self.matched, self.missing, self.extra = verify_identity(
            self.name, self._fm)
        self._ctx["verify"] = (self.ok, self.total, self.matched, self.missing, self.extra)
