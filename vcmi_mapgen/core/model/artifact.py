"""The artifact classes a map's treasure draws from."""

from dataclasses import dataclass
from typing import Literal

type ArtifactTier = Literal["treasure", "minor", "major", "relic"]

TIERS: tuple[ArtifactTier, ...] = ("treasure", "minor", "major", "relic")


@dataclass(frozen=True)
class ArtifactSet:
    """A combined artifact and the parts a hero assembles it from. `water` marks a set
    the game places only on a map with water."""

    name: str
    parts: tuple[str, ...]
    water: bool = False
