"""Print the price and the prize of every cut-off place on a few generated maps: the places a
gate, the sea or a portal cuts off, and where each map's artifact sets landed."""

import contextlib
import io
import statistics
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from vcmi_mapgen.cli.settings import Settings
from vcmi_mapgen.cli.steps import StepConfig, build_steps
from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import PlacedObject, Reward, Tile, footprint
from vcmi_mapgen.core.model.artifact import TIERS, ArtifactTier
from vcmi_mapgen.core.pipeline import Pipeline
from vcmi_mapgen.core.placement.rewards import LEVELS
from vcmi_mapgen.core.planning.pricing import CutoffPlace
from vcmi_mapgen.core.priors.effort import BANDS
from vcmi_mapgen.core.reading.value import ValueTable, value_of
from vcmi_mapgen.core.steps.portal.result import PortalResult
from vcmi_mapgen.core.steps.sets.result import SetsResult
from vcmi_mapgen.core.steps.treasure.result import TreasureResult
from vcmi_mapgen.corpus.priors import load_priors


@dataclass(frozen=True, slots=True)
class ReportOptions:
    """The maps the report generates: their seeds, side length and terrain model."""

    seeds: Sequence[int]
    size: int
    terrain: str


@dataclass(frozen=True, slots=True)
class PlaceRow:
    """One cut-off place: where it is, what it costs, what it holds and the level of each
    creature stack its Pandora's Boxes grant."""

    seed: int
    level: int
    zid: int
    place: CutoffPlace
    value: int
    arts: Sequence[ArtifactTier]
    stacks: Sequence[int]


@dataclass(frozen=True, slots=True)
class SetRow:
    """One set part on one map: the set, the part and the band of the slot it stands on."""

    seed: int
    name: str
    part: str
    band: int


type Spots = dict[tuple[int, Tile], PlacedObject]


def _stacks(levels: dict[str, int], place: CutoffPlace) -> list[int]:
    return [
        levels[name]
        for o in place.prizes
        if isinstance(o.payload, Reward)
        for name, _ in o.payload.creatures
        if name in levels
    ]


def _prize(
    catalog: Catalog, table: ValueTable, place: CutoffPlace, spots: Spots
) -> tuple[int, list[ArtifactTier]]:
    held = [o for h in place.held if (o := spots.get((h.level, h.tile))) is not None]
    prizes = [*place.prizes, *held]
    values = [value_of(catalog, table, o) for o in prizes]
    arts: list[ArtifactTier] = [
        table.artifacts[k] for o in prizes if (k := o.kind.lower()) in table.artifacts
    ]
    return max(values, default=0), arts


def _set_rows(seed: int, pipeline: Pipeline) -> list[SetRow]:
    return [
        SetRow(seed, s.name, o.kind, band)
        for s in pipeline.ctx.get(SetsResult, SetsResult()).sets
        for o, band in zip(s.parts, s.bands, strict=True)
    ]


def _places(pipeline: Pipeline) -> list[tuple[int, int, CutoffPlace]]:
    treasure = pipeline.ctx.get(TreasureResult, TreasureResult()).places
    portal = pipeline.ctx.get(PortalResult, PortalResult()).places
    return sorted(
        (level, zid, place)
        for found in (treasure, portal)
        for level, zones in found.items()
        for zid, place in zones.items()
    )


def _rows(
    catalog: Catalog, settings: Settings, report: ReportOptions
) -> tuple[list[PlaceRow], list[SetRow]]:
    priors = load_priors(settings.pp_dir, settings.pockets_file)
    table = ValueTable.of(catalog)
    levels = {name: lv for lv in LEVELS for name in catalog.monsters(lv)}
    rows: list[PlaceRow] = []
    set_rows: list[SetRow] = []
    for seed in report.seeds:
        pipeline = Pipeline(catalog, report.size)
        config = StepConfig(seed, report.size, subterrain=seed % 2 == 0, terrain=report.terrain)
        for name, step in build_steps(priors, config):
            _ = pipeline.add_step(step)
            if name == "sets":
                break
        with contextlib.redirect_stdout(io.StringIO()):
            map_state = pipeline.run()
        spots = {(o.level, t): o for o in map_state.objs for t, _ in footprint(o)}
        rows += [
            PlaceRow(
                seed,
                level,
                zid,
                place,
                *_prize(catalog, table, place, spots),
                _stacks(levels, place),
            )
            for level, zid, place in _places(pipeline)
        ]
        set_rows += _set_rows(seed, pipeline)
    return rows, set_rows


def place_lines(rows: Sequence[PlaceRow]) -> list[str]:
    """One line per cut-off place: what opens it, its effort, its band and its artifacts."""
    head = (
        f"{'seed':>4} {'lvl':>3} {'zone':>4} {'opener':>6} {'days':>4} {'guard':>5} "
        + f"{'total':>5} band  arts"
    )
    return [head] + [
        f"{r.seed:>4} {r.level:>3} {r.zid:>4} {r.place.opener:>6} {r.place.price.effort.days:>4} "
        + f"{r.place.price.effort.guard:>5} {r.place.price.effort.total:>5} "
        + f"{r.place.price.band:>4}  {', '.join(r.arts) or '-'}"
        for r in rows
    ]


def band_lines(rows: Sequence[PlaceRow]) -> list[str]:
    """One line per band: its places, the median of each place's top prize value, the
    artifact classes it drew and the creature levels its Pandora's Boxes grant."""
    lines = [f"{'band':>4} {'places':>6} {'top prize':>9}  artifacts by class | stacks by level"]
    for band in range(1, BANDS + 1):
        found = [r for r in rows if r.place.price.band == band]
        tally = Counter(a for r in found for a in r.arts)
        prize = statistics.median(r.value for r in found) if found else 0
        classes = " ".join(f"{t}={tally[t]}" for t in TIERS)
        stacks = Counter(lv for r in found for lv in r.stacks)
        grants = " ".join(f"L{lv}={stacks[lv]}" for lv in sorted(stacks)) or "-"
        lines.append(f"{band:>4} {len(found):>6} {prize:>9.0f}  {classes} | {grants}")
    return lines


def set_lines(rows: Sequence[SetRow]) -> list[str]:
    """One line per set on a map: its parts and the band of the slot each stands on."""
    by_set: dict[tuple[int, str], list[SetRow]] = {}
    for r in rows:
        by_set.setdefault((r.seed, r.name), []).append(r)
    lines = [f"{'seed':>4} {'set':<24} parts by band"]
    for (seed, name), parts in sorted(by_set.items()):
        bands = " ".join(f"{p.part}:{p.band}" for p in parts)
        lines.append(f"{seed:>4} {name:<24} {bands}")
    return lines


def effort_report(catalog: Catalog, settings: Settings, report: ReportOptions) -> None:
    rows, set_rows = _rows(catalog, settings, report)
    for line in [*place_lines(rows), "", *band_lines(rows), "", *set_lines(set_rows)]:
        print(line)
