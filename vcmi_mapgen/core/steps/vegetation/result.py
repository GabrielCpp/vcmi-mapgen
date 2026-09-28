"""VegetationStep's result."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class VegetationResult:
    """Diagnostic log lines for the CLI to print."""

    log: list[str] = field(default_factory=list)
