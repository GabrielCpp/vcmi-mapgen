"""BorderStep's result."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from vcmi_mapgen.core.model import Tile


@dataclass(frozen=True, slots=True)
class BorderResult:
    """Diagnostic log lines for the CLI to print, and each level's border guard tiles, which
    no later object may stand on."""

    log: list[str] = field(default_factory=list[str])
    guard_tiles: Mapping[int, frozenset[Tile]] = field(default_factory=dict[int, frozenset[Tile]])
