"""Mine the corpus gate estimator from two-level corpus maps."""

import math
from collections.abc import Iterable
from itertools import combinations

from vcmi_mapgen.core.model import MapState, Tile
from vcmi_mapgen.core.priors.gates import GateStats
from vcmi_mapgen.vcmi.catalog.roles import SUBTERRANEAN_GATE

MIN_GAP_QUANTILE = 0.25


MIN_AREA_STATS = 60


def _corpus_gates(fm: MapState) -> tuple[Tile, ...]:
    return tuple(
        sorted(
            (o.x, o.y)
            for o in fm.objs
            if o.level == 0 and (o.kind or "").lower().removesuffix(".def") == SUBTERRANEAN_GATE
        )
    )


def mine_gate_stats(maps: Iterable[MapState]) -> GateStats:
    """Corpus SUBTERRANEAN_GATE estimator over distinct two-level corpus maps with at least
    one gate. Gate count does not track underground area in the corpus, so the count is a
    draw from same-width maps rather than a per-tile rate. The spacing floor is the
    MIN_GAP_QUANTILE quantile of each multi-gate map's closest gate pair."""
    counts: dict[int, list[int]] = {}
    gaps: list[float] = []
    seen: set[tuple[int, tuple[Tile, ...]]] = set()
    for fm in maps:
        if len(fm.cells) < 2:
            continue
        if sum(1 for row in fm.cells[1] for c in row if c.t != 9) < MIN_AREA_STATS:
            continue
        gates = _corpus_gates(fm)
        if not gates or (fm.size, gates) in seen:
            continue
        seen.add((fm.size, gates))
        counts.setdefault(fm.size, []).append(len(gates))
        if len(gates) >= 2:
            gaps.append(min(math.dist(a, b) for a, b in combinations(gates, 2)) / fm.size)
    gaps.sort()
    frac = gaps[int(MIN_GAP_QUANTILE * (len(gaps) - 1))] if gaps else 0.0
    by_size = {w: sorted(ns) for w, ns in sorted(counts.items())}
    return GateStats(
        counts_by_size={w: tuple(ns) for w, ns in by_size.items()},
        min_gap_frac=frac,
        n_maps=len(seen),
    )
