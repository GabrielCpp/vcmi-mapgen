"""What a placed object carries beyond its kind: a guard's temper, a reward, a quest, a
scroll's spell, a starting town's buildings, or a dwelling's tie to its town. The export
turns each payload into the map format's own options."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Guard:
    """A hostile stack: it fights every hero and never joins one."""


@dataclass(frozen=True, slots=True)
class Reward:
    """A one-off payout: gold, experience, or `creatures` as (creature, count) stacks."""

    gold: int = 0
    experience: int = 0
    creatures: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True, slots=True)
class Quest:
    """Bring `artifact` and receive `reward`."""

    artifact: str
    reward: Reward


@dataclass(frozen=True, slots=True)
class Scroll:
    """A spell scroll that teaches `spell`."""

    spell: str


@dataclass(frozen=True, slots=True)
class Town:
    """A starting town: fort, tavern and the first two dwellings built, every core spell
    possible in its mage guild."""


@dataclass(frozen=True, slots=True)
class Dwelling:
    """A random dwelling that takes the faction of the town at `town`, as (x, y, level)."""

    town: tuple[int, int, int]


type Payload = Guard | Reward | Quest | Scroll | Town | Dwelling
