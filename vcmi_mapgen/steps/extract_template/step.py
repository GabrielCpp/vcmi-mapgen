"""ExtractTemplateStep — map -> shape-relative zone template."""
from __future__ import annotations

from vcmi_mapgen.pipeline import PipelineStep
from vcmi_mapgen.rebuild.engine import extract_template


class ExtractTemplateStep(PipelineStep):
    """Segment a map into same-terrain zones and record each zone's object pattern in
    a shape-relative frame.

    Config:
        name  Source map name (loaded from the corpus via kit.objects.load_faithful).

    Produces: ``template`` (dict).
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.template: dict = {}

    def run(self) -> None:
        self.template = extract_template(self.name)
