"""Read the remote distance of each corpus map size: the smallest king-step count at which
the median map of that size leaves almost none of its free land."""

import statistics
from collections import defaultdict
from collections.abc import Sequence

from vcmi_mapgen.core.model import MapState
from vcmi_mapgen.core.priors.remote import RemotePriors
from vcmi_mapgen.core.reading.remote import free_land, level_distance, remote_share

SHARE_CUT = 0.001
MAX_REACH = 12


def map_shares(state: MapState) -> list[float]:
    """The surface's share of free land at each step count from 0 to ``MAX_REACH``."""
    objs = [o for o in state.objs if o.level == 0]
    distance = level_distance(objs, state.size)
    free = free_land(state.terrain[0], objs)
    return [remote_share(distance, free, k) for k in range(MAX_REACH + 1)]


def mine_remote(maps: Sequence[MapState]) -> RemotePriors:
    """Per corpus map size, the smallest step count whose median share of free land falls
    under ``SHARE_CUT``."""
    by_size: defaultdict[int, list[list[float]]] = defaultdict(list)
    for state in maps:
        by_size[state.size].append(map_shares(state))
    reach: dict[int, int] = {}
    for size, rows in sorted(by_size.items()):
        medians = [statistics.median(r[k] for r in rows) for k in range(MAX_REACH + 1)]
        reach[size] = next((k for k, m in enumerate(medians) if m < SHARE_CUT), MAX_REACH)
    return RemotePriors(reach)
