"""PortalStep's result."""

from __future__ import annotations

from dataclasses import dataclass, field

from vcmi_mapgen.core.planning.pricing import CutoffPlace


@dataclass
class PortalResult:
    """Diagnostic log lines for the CLI to print, and every portal place, per level and zone
    id."""

    log: list[str] = field(default_factory=list)
    places: dict[int, dict[int, CutoffPlace]] = field(default_factory=dict)
