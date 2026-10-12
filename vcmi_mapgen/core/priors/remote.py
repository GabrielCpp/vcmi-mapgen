"""The remote distance per map size: the king steps past which free land counts as far
from every object worth the walk."""

from collections.abc import Mapping
from dataclasses import dataclass, field

REMOTE_REACH: Mapping[int, int] = {36: 4, 72: 5, 108: 5, 144: 6}


@dataclass(frozen=True, slots=True)
class RemotePriors:
    """The remote distance of each corpus map size."""

    reach: Mapping[int, int] = field(default_factory=lambda: dict(REMOTE_REACH))

    def at(self, size: int) -> int:
        """The remote distance of the corpus size nearest ``size``, the smaller on a tie."""
        nearest = min(self.reach, key=lambda s: (abs(s - size), s))
        return self.reach[nearest]
