import contextlib
import io
import statistics
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

from vcmi_mapgen.cli.settings import Settings
from vcmi_mapgen.cli.steps import StepConfig, build_steps
from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState
from vcmi_mapgen.core.pipeline import Pipeline
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.reading.claimed import CLAIM_DAYS, claims_of, owner_maps, worst_share
from vcmi_mapgen.core.reading.contest import CONTEST, FAR_FLOOR, enemy_pairs, gold_mines
from vcmi_mapgen.core.reading.ground import TownKey
from vcmi_mapgen.core.reading.mines import land_area
from vcmi_mapgen.core.reading.places import owners_of
from vcmi_mapgen.core.reading.promise import player_maps
from vcmi_mapgen.core.reading.repeats import NEAR, SIDE, nearest_copies, repeat_share
from vcmi_mapgen.core.reading.spread import Spread, columns
from vcmi_mapgen.core.reading.vector import Vector, map_vector
from vcmi_mapgen.core.reading.way import close_share, player_ways, rare_mines
from vcmi_mapgen.corpus.maps import named_corpus_maps
from vcmi_mapgen.corpus.mine.counts import map_mines, map_towns
from vcmi_mapgen.corpus.mine.places import map_players
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

type Columns = Mapping[str, Sequence[float]]
type Named = tuple[str, MapState]


def count_reading(catalog: Catalog, state: MapState, players: int, priors: Priors) -> Vector:
    """The resource mines and the towns on ``state``, each beside its curve's expectation at
    the map's land and ``players``, then the share of repeated visitables with a copy of
    their kind within NEAR and within SIDE tiles."""
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


def _generated(catalog: Catalog, priors: Priors, config: StepConfig) -> Vector:
    pipeline = Pipeline(catalog, config.size)
    for _name, step in build_steps(priors, config):
        _ = pipeline.add_step(step)
    start = time.perf_counter()
    with contextlib.redirect_stdout(io.StringIO()):
        state = pipeline.run()
    seconds = time.perf_counter() - start
    counts = count_reading(catalog, state, config.players, priors)
    ways = way_reading(catalog, state, priors)
    owners = owners_of(state)
    value = value_reading(catalog, state, owners, priors)
    return {**map_vector(catalog, state, owners), **counts, **ways, **value, SECONDS: seconds}


def _corpus_vector(catalog: Catalog, h3m_dir: Path, priors: Priors, named: Named) -> Vector:
    name, state = named
    players = map_players(h3m_dir, name)
    counts = count_reading(catalog, state, players.players, priors)
    value = value_reading(catalog, state, players.owners, priors)
    return {**map_vector(catalog, state, players.owners), **counts, **value}


def _corpus(catalog: Catalog, settings: Settings, size: int, priors: Priors) -> list[Vector]:
    named = named_corpus_maps(settings.maps_dir)
    sized = [(name, state) for name, state in named if state.size == size] or named
    return [_corpus_vector(catalog, settings.h3m_dir, priors, n) for n in sized]


def _cell(spread: Spread | None) -> str:
    if spread is None:
        return "-"
    return f"{spread.median:.3f} [{spread.q1:.3f}, {spread.q3:.3f}]"


def _median(values: Sequence[float] | None) -> str:
    return f"{statistics.median(values):.3f}" if values else "-"


def table_lines(corpus: Columns, generated: Columns) -> list[str]:
    """One row per reading: the corpus median and quartiles, then the generated median."""
    readings = list(dict.fromkeys([*corpus, *generated]))
    head = f"{'reading':22} {'corpus median [q1, q3]':28} {'generated':>9}"
    rows = [
        f"{r:22} {_cell(Spread.of(corpus.get(r, ()))):28} {_median(generated.get(r)):>9}"
        for r in readings
    ]
    return [head, *rows]


def readings(
    catalog: Catalog, settings: Settings, seeds: Sequence[int], size: int, players: int = 2
) -> None:
    priors = load_priors(settings.pp_dir, settings.pockets_file)
    configs = [StepConfig(seed, size, players=players) for seed in seeds]
    vectors = [_generated(catalog, priors, config) for config in configs]
    generated = columns(vectors)
    print(f"generated {len(vectors)} maps")
    for seed, vector in zip(seeds, vectors, strict=True):
        print(count_line(seed, vector))
    corpus_vectors = _corpus(catalog, settings, size, priors)
    corpus = columns(corpus_vectors)
    print(f"read {len(corpus_vectors)} corpus maps")
    for line in table_lines(corpus, generated):
        print(line)
