from collections.abc import Iterator
from collections.abc import Set as AbstractSet
from dataclasses import dataclass

import pytest

from vcmi_mapgen.cli.settings import load_settings
from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import Tile
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.pipeline import ZoneWorkspace
from vcmi_mapgen.core.placement.site import LevelField, ZoneSite
from vcmi_mapgen.core.steps.gameplay.draw import DrawSpec, ZoneDrawer
from vcmi_mapgen.core.steps.gameplay.economy import BASIC_MINE_RES, Ledger, tie_dwellings
from vcmi_mapgen.core.steps.gameplay.step import place_attractions, place_mines, place_town
from vcmi_mapgen.vcmi.catalog import objects as ON
from vcmi_mapgen.vcmi.catalog.adapter import VcmiCatalog
from vcmi_mapgen.vcmi.config import EMPTY_CONFIG, load_config
from vcmi_mapgen.vcmi.install import InstallNotFoundError


@pytest.fixture(autouse=True, scope="session")
def _bound_catalog() -> Iterator[None]:
    try:
        ON.use_config(load_config(load_settings().install()))
    except InstallNotFoundError:
        ON.use_config(EMPTY_CONFIG)
    yield
    ON.use_config(EMPTY_CONFIG)


@pytest.fixture(scope="session")
def catalog(_bound_catalog: None) -> Catalog:
    return VcmiCatalog()


@dataclass(frozen=True, slots=True)
class OpenZone:
    """One zone of open land to draw outside any pipeline: its tiles, its terrain, and
    whether a player starts in it."""

    ts: AbstractSet[Tile]
    terrain: str
    player: bool = False


@dataclass(frozen=True, slots=True)
class OpenZonePlacer:
    catalog: Catalog

    def __call__(self, zone: OpenZone, seed: int, ledger: Ledger | None = None) -> ZoneWorkspace:
        """Draw and place one zone of open land with no vegetation and a one-tile web at its
        top-left corner, outside any pipeline. Returns its workspace after write-back."""
        ts, terrain, player = zone.ts, zone.terrain, zone.player
        w = max(x for x, _y in ts) + 1
        h = max(y for _x, y in ts) + 1
        zw = ZoneWorkspace(
            terrain=terrain,
            ts=frozenset(ts),
            ts_full=frozenset(ts),
            prot=frozenset({min(ts)}),
            open_set=frozenset(ts),
            passable=frozenset(ts),
        )
        lf = LevelField.build(0, [[int(Terrain.GRASS)] * w for _ in range(h)], [], lambda _o: True)
        site = ZoneSite(self.catalog, 1, zw, lf, seed)
        ledger = ledger or Ledger(set(BASIC_MINE_RES), 1, 0)
        spec = DrawSpec(1, terrain, len(ts), player=player)
        draw = ZoneDrawer(self.catalog, spec, site.st, ledger, seed).draw()
        place_town(site, draw, player)
        place_mines(site, draw, ledger, set())
        place_attractions(site, draw)
        site.write_back()
        tie_dwellings(self.catalog, zw.gobjs)
        return zw


@pytest.fixture
def open_zone(catalog: Catalog) -> OpenZonePlacer:
    return OpenZonePlacer(catalog)
