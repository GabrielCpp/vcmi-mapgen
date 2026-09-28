"""PortalStep's result."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PortalResult:
    """Diagnostic log lines for the CLI to print."""

    log: list[str] = field(default_factory=list)
