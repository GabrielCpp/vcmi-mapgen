"""The corpus macro terrain statistics the macro zone growth draws from."""

from dataclasses import dataclass


@dataclass(slots=True)
class MacroStats:
    areas: list[int]
    barrier_fracs: list[float]
    terr_share: dict[int, int]
    adj: dict[str, int]
    nzones: list[int]
