"""Water measured against place geometry, the same way on a corpus map and a generated one:
each tile's features for the logistic odds of water, and one map's water target."""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

import numpy as np
from numpy.typing import NDArray

from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.priors.water import WaterTarget

NAMES = (
    "bias",
    "log_reach",
    "border",
    "strait",
    "border_x_strait",
    "inner",
    "inner_x_edge_water",
    "town_near",
    "water_n4",
    "water_diag",
)
STATIC = 8
MAX_REACH = 6.0
TOWN_RANGE = 4.0
MASS_SHARE = 0.05

type Floats = NDArray[np.float64]
type Mask = NDArray[np.bool_]
type Labels = NDArray[np.int64]


@dataclass(frozen=True, slots=True)
class WaterPlace:
    """A place as the water features see it: its centre tile, the radius of a disc of its
    area, and the land mass it belongs to."""

    centre: Tile
    radius: float
    mass: int


def static_features(
    shape: tuple[int, int],
    places: Sequence[WaterPlace],
    towns: Sequence[Tile],
    edge_water: float,
) -> Floats:
    """One row of the static features per tile, row-major: the reach to the nearest place
    in its radii, the border ratio between the two nearest places, whether those two lie on
    different masses, the distance to the map edge in half sides, and the nearness of a
    town."""
    h, w = shape
    ys: Labels = np.repeat(np.arange(h, dtype=np.int64), w)
    xs: Labels = np.tile(np.arange(w, dtype=np.int64), h)
    tiles: Floats = np.stack([xs, ys], axis=1).astype(np.float64)
    centres = np.array([p.centre for p in places], dtype=np.float64)
    radii = np.array([p.radius for p in places], dtype=np.float64)
    masses = np.array([p.mass for p in places], dtype=np.int64)
    d = cast("Floats", np.linalg.norm(tiles[:, None, :] - centres[None, :, :], axis=2))
    rows = np.arange(len(tiles))
    n1: NDArray[np.intp] = np.zeros(len(tiles), dtype=np.intp)
    n2 = n1
    if len(places) > 1:
        order = np.argsort(d, axis=1)
        n1, n2 = order[:, 0], order[:, 1]
    d1: Floats = d[rows, n1]
    d2: Floats = d[rows, n2]
    reach: Floats = np.log1p(np.minimum(d1 / np.maximum(radii[n1], 1.0), MAX_REACH))
    border: Floats = d1 / np.maximum(d2, 1e-6) if len(places) > 1 else np.zeros(len(tiles))
    strait = cast("Mask", masses[n1] != masses[n2]).astype(np.float64)
    edge: Labels = np.minimum(np.minimum(xs, ys), np.minimum(w - 1 - xs, h - 1 - ys))
    inner = edge / (min(h, w) / 2.0)
    town_near: Floats = np.zeros(len(tiles))
    if towns:
        tc = np.array(towns, dtype=np.float64)
        dt = cast("Floats", np.linalg.norm(tiles[:, None, :] - tc[None, :, :], axis=2))
        town_near = np.exp(-cast("Floats", np.min(dt, axis=1)) / TOWN_RANGE)
    return np.stack(
        [
            np.ones(len(tiles)),
            reach,
            border,
            strait,
            border * strait,
            inner,
            inner * edge_water,
            town_near,
        ],
        axis=1,
    )


def _share(pad: Floats, inside: Floats, offsets: Sequence[Tile], shape: Tile) -> Floats:
    h, w = shape
    num = np.zeros((h, w))
    den = np.zeros((h, w))
    for dx, dy in offsets:
        num += pad[1 + dy : 1 + dy + h, 1 + dx : 1 + dx + w]
        den += inside[1 + dy : 1 + dy + h, 1 + dx : 1 + dx + w]
    return (num / den).ravel()


def neighbour_features(water: Mask) -> Floats:
    """One row per tile, row-major: the share of water among its in-bounds 4-neighbours and
    among its in-bounds diagonal neighbours."""
    h, w = water.shape
    pad = np.pad(water.astype(np.float64), 1)
    inside = np.pad(np.ones((h, w)), 1)
    n4 = _share(pad, inside, ((1, 0), (-1, 0), (0, 1), (0, -1)), (h, w))
    nd = _share(pad, inside, ((1, 1), (-1, 1), (1, -1), (-1, -1)), (h, w))
    return np.stack([n4, nd], axis=1)


def edge_water_share(water: Mask) -> float:
    """The share of water on the map's outer ring of tiles."""
    ring: Mask = np.concatenate([water[0, :], water[-1, :], water[1:-1, 0], water[1:-1, -1]])
    return float(np.mean(ring))


def land_labels(land: Mask) -> Labels:
    """The 4-connected land components numbered from 1, and 0 off the land."""
    h, w = land.shape
    lab = np.zeros((h, w), dtype=np.int64)
    n = 0
    for y0 in range(h):
        for x0 in range(w):
            if not land[y0, x0] or lab[y0, x0]:
                continue
            n += 1
            lab[y0, x0] = n
            stack = [(x0, y0)]
            while stack:
                x, y = stack.pop()
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if 0 <= nx < w and 0 <= ny < h and land[ny, nx] and not lab[ny, nx]:
                        lab[ny, nx] = n
                        stack.append((nx, ny))
    return lab


def big_masses(land: Mask) -> int:
    """The land components that each hold at least 5% of the land."""
    areas: Labels = np.bincount(land_labels(land).ravel())[1:]
    land_tiles = int(np.count_nonzero(land))
    return int(np.count_nonzero(areas >= MASS_SHARE * max(1, land_tiles)))


def water_target(water: Mask, rock: Mask) -> WaterTarget:
    """One map's water share, edge water share and big land masses, with rock off the
    land."""
    return WaterTarget(float(np.mean(water)), edge_water_share(water), big_masses(~water & ~rock))


def water_places(labels: Sequence[Sequence[int]], masses: Labels) -> list[WaterPlace]:
    """Each labelled place as the water features see it, in label order. Its centre is its
    tile nearest its mean, and its mass is the component under that centre."""
    tiles: dict[int, list[Tile]] = {}
    for y, row in enumerate(labels):
        for x, p in enumerate(row):
            if p >= 0:
                tiles.setdefault(p, []).append((x, y))
    out: list[WaterPlace] = []
    for _, ts in sorted(tiles.items()):
        cx = sum(t[0] for t in ts) / len(ts)
        cy = sum(t[1] for t in ts) / len(ts)
        centre = min(ts, key=lambda t: (t[0] - cx) ** 2 + (t[1] - cy) ** 2)
        mass = cast("np.int64", masses[centre[1], centre[0]])
        out.append(WaterPlace(centre, math.sqrt(len(ts) / math.pi), int(mass)))
    return out
