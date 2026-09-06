"""VerifyStep — multiset-compare a rebuilt map's objects to its source (the bit-exact
identity guarantee's check)."""
from __future__ import annotations

from vcmi_mapgen.pipeline import PipelineStep
from vcmi_mapgen.rebuild.engine import verify_identity


class VerifyStep(PipelineStep):
    """Verify a rebuilt map is bit-exact identical to its source.

    Config:
        name  Source map name (loaded from the corpus for comparison).

    inject(fm): ``fm`` (RebuildMapStep's output).

    Produces: ``ok`` (bool), ``total``, ``matched`` (int), ``missing``, ``extra``
    (Counters of the objects that didn't match).
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.ok: bool = False
        self.total: int = 0
        self.matched: int = 0
        self.missing = None
        self.extra = None
        self._fm: dict = {}

    def inject(self, *, fm: dict) -> None:
        self._fm = fm

    def run(self) -> None:
        self.ok, self.total, self.matched, self.missing, self.extra = verify_identity(
            self.name, self._fm)
