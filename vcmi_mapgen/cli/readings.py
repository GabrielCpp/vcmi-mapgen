import contextlib
import io
import statistics
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from vcmi_mapgen.cli.settings import Settings
from vcmi_mapgen.cli.steps import StepConfig, build_steps
from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState
from vcmi_mapgen.core.pipeline import Pipeline
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.priors.spacing import SpacingFit, SpacingPriors
from vcmi_mapgen.core.reading.claimed import CLAIM_DAYS, claims_of, owner_maps, worst_share
from vcmi_mapgen.core.reading.contest import CONTEST, FAR_FLOOR, enemy_pairs, gold_mines
from vcmi_mapgen.core.reading.ground import TownKey
from vcmi_mapgen.core.reading.mines import land_area
from vcmi_mapgen.core.reading.places import owners_of
from vcmi_mapgen.core.reading.promise import player_maps
from vcmi_mapgen.core.reading.repeats import (
    NEAR,
    SIDE,
    copy_spacing,
    kind_key,
    nearest_copies,
    repeat_share,
)
from vcmi_mapgen.core.reading.spread import MIN_MAPS, Column, Spread, columns, nearest_columns
from vcmi_mapgen.core.reading.vector import Vector, map_vector
from vcmi_mapgen.core.reading.way import close_share, player_ways, rare_mines
from vcmi_mapgen.corpus.maps import named_corpus_maps
from vcmi_mapgen.corpus.mine.counts import map_mines, map_towns
from vcmi_mapgen.corpus.mine.places import MapPlayers, map_players
from vcmi_mapgen.corpus.priors import load_priors

SECONDS = "seconds"
MINES = "resource mines"
CURVE = "mine curve"
TOWNS = "towns"
TOWN_CURVE = "town curve"
CLOSE_RARE = "close rare mines"
REPEATS = "repeating ways"
GOLD_MINES = "gold mines"
GOLD_NEAR = "gold near home"
GOLD_OPEN = "uncontested gold"
NEAR_COPIES = "copies within 10"
SIDE_COPIES = "copies within 6"
SPACED_KINDS = "kinds spaced"
CROWDED = "copies crowded"

type Columns = Mapping[str, Sequence[float]]


type Copies = list[tuple[str, str, float]]


def copies_of(catalog: Catalog, state: MapState) -> Copies:
    """Each spaced copy on ``state`` with its kind key, its purpose and its u."""
    return [(kind_key(k), p, u) for k, p, u in copy_spacing(catalog, state)]


def spacing_reading(copies: Copies, priors: Priors) -> Vector:
    """Over the kinds with a spacing fit, the share whose median u lies within the fit's p10
    and p90, and over their copies the share whose u is under the fit's p10. Empty when no
    kind has a fit."""
    by_kind: defaultdict[tuple[str, str], list[float]] = defaultdict(list)
    for key, purpose, u in copies:
        by_kind[(key, purpose)].append(u)
    kinds: list[tuple[SpacingFit, float]] = []
    crowded = total = 0
    for (key, purpose), us in by_kind.items():
        fit = priors.spacing.fit_for(key, purpose)
        if fit is None:
            continue
        kinds.append((fit, statistics.median(us)))
        crowded += sum(u < fit.p10 for u in us)
        total += len(us)
    if not kinds:
        return {}
    return {
        SPACED_KINDS: sum(fit.p10 <= median <= fit.p90 for fit, median in kinds) / len(kinds),
        CROWDED: crowded / total,
    }


def count_reading(
    catalog: Catalog, state: MapState, players: int, priors: Priors, copies: Copies
) -> Vector:
    """The resource mines and the towns on ``state``, each beside its curve's expectation at
    the map's land and ``players``, then the share of repeated visitables with a copy of
    their kind within NEAR and within SIDE tiles. The kinds spaced within their corpus p10 to
    p90 and the copies crowded under the p10 of their fit follow when a kind has one."""
    land = land_area(state)
    gaps = nearest_copies(catalog, state.objs)
    return {
        MINES: float(map_mines(catalog, state)),
        CURVE: priors.mines.expected(land, players),
        TOWNS: float(map_towns(catalog, state)),
        TOWN_CURVE: priors.towns.expected(land, players),
        CLOSE_RARE: close_share(catalog, state.objs),
        NEAR_COPIES: repeat_share(gaps, NEAR),
        SIDE_COPIES: repeat_share(gaps, SIDE),
        **spacing_reading(copies, priors),
    }


def way_reading(catalog: Catalog, state: MapState, priors: Priors) -> Vector:
    """The players whose way out repeats a rare resource before it meets every one the map
    offers, then the gold mines, those within the far floor of a home and those past the
    contest bound."""
    offered = {res for res, _o in rare_mines(catalog, state.objs)}
    maps = player_maps(catalog, state, priors.effort.toll)
    ways = player_ways(catalog, state.objs, maps)
    gold = gold_mines(catalog, state.objs, maps, enemy_pairs(len(maps)))
    return {
        REPEATS: float(sum(w.repeat(offered) is not None for w in ways)),
        GOLD_MINES: float(len(gold)),
        GOLD_NEAR: float(sum(g.days is not None and g.days <= FAR_FLOOR for g in gold)),
        GOLD_OPEN: float(sum(g.contest is None or g.contest > CONTEST for g in gold)),
    }


def claimed_name(days: int) -> str:
    """The reading of the worst player's value claimed within ``days`` over the best's."""
    return f"claimed within {days}"


def value_reading(
    catalog: Catalog, state: MapState, owners: Mapping[TownKey, int], priors: Priors
) -> Vector:
    """Per horizon of CLAIM_DAYS, the worst player's value claimed first over the best
    player's, empty when fewer than two players own a town."""
    maps = owner_maps(catalog, state, owners, priors.effort.toll)
    if len(maps) < 2:
        return {}
    claims = claims_of(catalog, state, maps)
    shares = {claimed_name(d): worst_share(claims, d) for d in CLAIM_DAYS}
    return {name: share for name, share in shares.items() if share is not None}


def count_line(seed: int, vector: Vector) -> str:
    """One generated map's resource mines and towns, each beside its curve's expectation,
    then its repeating ways, its share of rare mines with one of their resource close by,
    its gold mines with those near a home and those uncontested, and its shares of repeated
    visitables with a copy close by."""
    mines, curve = vector[MINES], vector[CURVE]
    towns, town_curve = vector[TOWNS], vector[TOWN_CURVE]
    return (
        f"seed {seed}: {mines:.0f} resource mines, curve {curve:.1f}, ratio {mines / curve:.2f};"
        f" {towns:.0f} towns, curve {town_curve:.1f}, ratio {towns / town_curve:.2f};"
        f" {vector.get(REPEATS, 0):.0f} ways repeat, close rare share {vector[CLOSE_RARE]:.2f};"
        f" {vector.get(GOLD_MINES, 0):.0f} gold, {vector.get(GOLD_NEAR, 0):.0f} near home,"
        f" {vector.get(GOLD_OPEN, 0):.0f} uncontested;"
        f" copies within 10 {vector[NEAR_COPIES]:.2f}, within 6 {vector[SIDE_COPIES]:.2f}"
    )


def _generated(catalog: Catalog, priors: Priors, config: StepConfig) -> tuple[Vector, Copies]:
    pipeline = Pipeline(catalog, config.size)
    for _name, step in build_steps(priors, config):
        _ = pipeline.add_step(step)
    start = time.perf_counter()
    with contextlib.redirect_stdout(io.StringIO()):
        state = pipeline.run()
    seconds = time.perf_counter() - start
    copies = copies_of(catalog, state)
    counts = count_reading(catalog, state, config.players, priors, copies)
    ways = way_reading(catalog, state, priors)
    owners = owners_of(state)
    value = value_reading(catalog, state, owners, priors)
    vector = {**map_vector(catalog, state, owners), **counts, **ways, **value, SECONDS: seconds}
    return vector, copies


def _corpus_vector(
    catalog: Catalog, priors: Priors, state: MapState, players: MapPlayers
) -> Vector:
    copies = copies_of(catalog, state)
    counts = count_reading(catalog, state, players.players, priors, copies)
    value = value_reading(catalog, state, players.owners, priors)
    return {**map_vector(catalog, state, players.owners), **counts, **value}


@dataclass(frozen=True, slots=True)
class CorpusSide:
    """The corpus maps a generated map reads against: their side, None when no corpus map
    shares the generated side and every side counts, and each map's player count and
    reading vector."""

    side: int | None
    maps: Sequence[tuple[int, Vector]]

    def line(self, players: int) -> str:
        side = f"side {self.side}" if self.side is not None else "every side"
        return (
            f"read {len(self.maps)} corpus maps of {side}; each reading keeps the player"
            f" counts nearest {players} until {MIN_MAPS} maps read it"
        )


def _corpus(catalog: Catalog, settings: Settings, size: int, priors: Priors) -> CorpusSide:
    named = named_corpus_maps(settings.maps_dir)
    sized = [(name, state) for name, state in named if state.size == size]
    maps: list[tuple[int, Vector]] = []
    for name, state in sized or named:
        players = map_players(settings.h3m_dir, name)
        maps.append((players.players, _corpus_vector(catalog, priors, state, players)))
    return CorpusSide(size if sized else None, maps)


def _cell(spread: Spread | None) -> str:
    if spread is None:
        return "-"
    return f"{spread.median:.3f} [{spread.q1:.3f}, {spread.q3:.3f}]"


def _players(column: Column | None) -> str:
    return ",".join(str(p) for p in column.players) if column is not None else "-"


def _flag(spread: Spread | None, values: Sequence[float] | None) -> str:
    if spread is None or not values:
        return ""
    median = statistics.median(values)
    if median < spread.q1:
        return "below"
    if median > spread.q3:
        return "above"
    return ""


def _median(values: Sequence[float] | None) -> str:
    return f"{statistics.median(values):.3f}" if values else "-"


def table_lines(corpus: Mapping[str, Column], generated: Columns) -> list[str]:
    """One row per reading: the corpus median and quartiles, the player counts and the
    number of the corpus maps they come from, then the generated median, flagged when it
    sits below or above the quartiles."""
    readings = list(dict.fromkeys([*corpus, *generated]))
    head = (
        f"{'reading':22} {'corpus median [q1, q3]':28} {'players':>7} {'maps':>4} {'generated':>9}"
    )
    rows: list[str] = []
    for r in readings:
        column, values = corpus.get(r), generated.get(r)
        spread = Spread.of(column.values) if column is not None else None
        maps = str(spread.n) if spread is not None else "-"
        row = f"{r:22} {_cell(spread):28} {_players(column):>7} {maps:>4} {_median(values):>9}"
        rows.append(f"{row} {_flag(spread, values)}".rstrip())
    return [head, *rows]


def spacing_lines(
    corpus: SpacingPriors, generated: Mapping[tuple[str, str], Sequence[float]]
) -> list[str]:
    """One row per kind seen on the generated maps, ordered by purpose and kind: the corpus
    sample count and median u with its p10 and p90 (marked pool when the purpose's pool
    stands in), then the generated count and median u, flagged below or above when the
    median leaves the corpus p10 to p90, and the share of the pooled u values under the fit's
    p10 as crowded."""
    head = (
        f"{'kind':34} {'purpose':14} {'corpus n':>8} {'corpus u median [p10, p90]':28}"
        f" {'gen n':>5} {'gen median':>10} {'crowded':>7}"
    )
    rows: list[str] = []
    for (key, purpose), us in sorted(generated.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        fit = corpus.fit_for(key, purpose)
        median = statistics.median(us)
        if fit is None:
            cell, n, flag, crowded = "-", "-", "", "-"
        else:
            pool = "" if key in corpus.kinds else " pool"
            cell = f"{fit.p50:.3f} [{fit.p10:.3f}, {fit.p90:.3f}]{pool}"
            n = str(fit.n)
            crowded = f"{sum(u < fit.p10 for u in us) / len(us):.2f}"
            flag = "below" if median < fit.p10 else "above" if median > fit.p90 else ""
        row = f"{key:34} {purpose:14} {n:>8} {cell:28} {len(us):>5} {median:>10.3f} {crowded:>7}"
        rows.append(f"{row} {flag}".rstrip())
    return [head, *rows]


def readings(
    catalog: Catalog, settings: Settings, seeds: Sequence[int], size: int, players: int = 2
) -> None:
    priors = load_priors(settings.pp_dir, settings.pockets_file)
    configs = [StepConfig(seed, size, players=players) for seed in seeds]
    runs = [_generated(catalog, priors, config) for config in configs]
    vectors = [vector for vector, _copies in runs]
    pooled: defaultdict[tuple[str, str], list[float]] = defaultdict(list)
    for _vector, copies in runs:
        for key, purpose, u in copies:
            pooled[(key, purpose)].append(u)
    generated = columns(vectors)
    print(f"generated {len(vectors)} maps")
    for seed, vector in zip(seeds, vectors, strict=True):
        print(count_line(seed, vector))
    corpus = _corpus(catalog, settings, size, priors)
    print(corpus.line(players))
    for line in table_lines(nearest_columns(corpus.maps, players), generated):
        print(line)
    print()
    for line in spacing_lines(priors.spacing, pooled):
        print(line)
