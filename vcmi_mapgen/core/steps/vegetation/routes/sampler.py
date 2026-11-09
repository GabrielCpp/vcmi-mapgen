"""The routes sampler: the open ground of one zone drawn first, as bands along a net of
near-straight routes between its ways in and waypoints spread over it, and decorations
planted on the rest without spilling onto it."""

import math
import random
from typing import cast, final

import numpy as np
from numpy.typing import NDArray

from vcmi_mapgen.core.grid.reach import STEPS8, distances
from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.planning.web import ZoneRef
from vcmi_mapgen.core.steps.vegetation.canvas import ZoneCanvas, zone_rng
from vcmi_mapgen.core.steps.vegetation.model import VegModel
from vcmi_mapgen.core.steps.vegetation.planting import Planter, plantable, planting_plan
from vcmi_mapgen.core.steps.vegetation.routes.net import route_net, waypoints
from vcmi_mapgen.core.steps.vegetation.sampler import SampleOptions, ZoneGrowth

SPAN = 0.6
BEND = 1.0
BAND = 1
BLUR = 2
TOP_UP = 3


def _box(a: NDArray[np.float64]) -> NDArray[np.float64]:
    h, w = a.shape
    p = np.pad(a, BLUR, mode="edge")
    out = np.zeros_like(a)
    for dy in range(2 * BLUR + 1):
        for dx in range(2 * BLUR + 1):
            out += p[dy : dy + h, dx : dx + w]
    return out / (2 * BLUR + 1) ** 2


def _blurred(h: int, w: int, rng: random.Random) -> NDArray[np.float64]:
    """Uniform noise over an `h` x `w` box, box-blurred twice by BLUR and scaled to unit
    spread."""
    a = _box(_box(np.array([rng.random() for _ in range(w * h)], dtype=np.float64).reshape(h, w)))
    sd = cast(float, a.std())
    mean = cast(float, a.mean())
    return (a - mean) / sd if sd > 0 else a * 0


@final
class RoutesSampler:
    def sample(self, zone: ZoneRef, model: VegModel, seed: int, opts: SampleOptions) -> ZoneGrowth:
        """Draw the zone's route net, then cover the corpus blocked share of each edge bin
        with decorations on the tiles farthest from every route. The routes and the ground
        within BAND of them stay free of every blocking cell, and the `border` tiles close
        as with every sampler. While the decorations block fewer tiles than the plan holds,
        the plan grows by the next tiles farthest from the routes, up to TOP_UP times."""
        if not model.cats:
            return [], set(), set()
        canvas = ZoneCanvas(zone, model, opts)
        rng = zone_rng(zone, seed)
        planter = Planter(canvas, model, rng)
        ts = zone.ts
        room = set(ts) - opts.forbid - set(opts.border) - opts.impassable
        ways_in = {
            (x, y)
            for x, y in canvas.prot & ts
            if (x, y) in room and any((x + dx, y + dy) not in ts for dx, dy in STEPS8)
        }
        nodes = waypoints(ways_in, room, SPAN * math.sqrt(len(ts)))
        routes = route_net(nodes, room)
        d = _route_distance(canvas, routes, room)
        field = cast(NDArray[np.float64], -(d + BEND * _blurred(canvas.H, canvas.W, rng)))
        on_route: NDArray[np.bool_] = d <= 0
        target = planting_plan(canvas, model, field, on_route)
        near: NDArray[np.bool_] = d <= BAND
        return _cover_to_count(planter, target, plantable(canvas) & ~target & near, field)


def _cover_to_count(
    planter: Planter,
    target: NDArray[np.bool_],
    keep: NDArray[np.bool_],
    field: NDArray[np.float64],
) -> ZoneGrowth:
    """Cover `target` off `keep`, then, while fewer plantable tiles are blocked than
    `target` holds, grow it by the free tiles where `field` is lowest and cover again, up to
    TOP_UP times."""
    canvas = planter.canvas
    dom = plantable(canvas)
    want = np.count_nonzero(target)
    growth = planter.cover(target, keep)
    for _ in range(TOP_UP):
        short = want - np.count_nonzero(canvas.blkcnt[dom])
        spare = dom & ~target & ~keep
        if short <= 0 or not bool(spare.any()):
            break
        ranked = np.sort(field[spare])
        cut = cast(float, ranked[min(short, len(ranked)) - 1])
        target = target | (spare & (field <= cut))
        growth = planter.cover(target, keep)
    return growth


def _route_distance(canvas: ZoneCanvas, routes: set[Tile], room: set[Tile]) -> NDArray[np.float64]:
    """The 8-connected steps through `room` from each canvas tile to the nearest route,
    and the canvas's span past it for a tile no route reaches."""
    d = np.full((canvas.H, canvas.W), float(canvas.W + canvas.H))
    for (x, y), steps in distances(room, routes, STEPS8).items():
        d[y - canvas.y0, x - canvas.x0] = steps
    return d
