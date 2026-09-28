from collections.abc import Iterator
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from pathlib import Path

import pytest

from vcmi_mapgen.cli.settings import Settings, load_settings
from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState, Tile
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.placement.site import LevelField, PlacedZone, SiteZone, ZoneSite
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.priors.gameplay import GameplayStats
from vcmi_mapgen.core.steps.gameplay.draw import DrawSpec, ZoneDrawer
from vcmi_mapgen.core.steps.gameplay.economy import BASIC_MINE_RES, Ledger, tie_dwellings
from vcmi_mapgen.core.steps.gameplay.step import place_attractions, place_mines, place_town
from vcmi_mapgen.corpus import gameplay, vegetation
from vcmi_mapgen.corpus.maps import corpus_path, load_corpus_map
from vcmi_mapgen.corpus.priors import load_priors
from vcmi_mapgen.corpus.tiler import load_tiler
from vcmi_mapgen.vcmi.catalog import objects as ON
from vcmi_mapgen.vcmi.catalog.adapter import VcmiCatalog
from vcmi_mapgen.vcmi.config import EMPTY_CONFIG, load_config
from vcmi_mapgen.vcmi.install import InstallNotFoundError, VcmiInstall
from vcmi_mapgen.vcmi.tiles import TilerTables

SETTINGS = load_settings()


def find_install() -> VcmiInstall | None:
    """The local VCMI install, or None when this machine has none."""
    try:
        return SETTINGS.install()
    except InstallNotFoundError:
        return None


def corpus_tiler() -> TilerTables:
    """The mined corpus tiler tables."""
    return load_tiler(SETTINGS.pp_dir)


def corpus_map_path(name: str) -> Path:
    """The ``.vmap`` path of one corpus map."""
    return Path(corpus_path(SETTINGS.maps_dir, name))


def corpus_map(name: str) -> MapState:
    """One corpus map, loaded."""
    return load_corpus_map(SETTINGS.maps_dir, name)


def gameplay_mined() -> bool:
    """Whether the level 0 gameplay statistics have been mined."""
    return gameplay.stats_path(SETTINGS.pp_dir, 0).exists()


def vegetation_mined() -> bool:
    """Whether the grass vegetation statistics have been mined."""
    return vegetation.stats_path(SETTINGS.pp_dir, "grass").exists()


@pytest.fixture(scope="session")
def settings() -> Settings:
    return SETTINGS


@pytest.fixture(scope="session")
def pp_dir() -> Path:
    """The mined corpus statistics directory."""
    return SETTINGS.pp_dir


@pytest.fixture(scope="session")
def maps_dir() -> Path:
    """The corpus maps directory."""
    return SETTINGS.maps_dir


@pytest.fixture(autouse=True, scope="session")
def _bound_catalog() -> Iterator[None]:
    install = find_install()
    ON.use_config(load_config(install) if install is not None else EMPTY_CONFIG)
    yield
    ON.use_config(EMPTY_CONFIG)


@pytest.fixture(scope="session")
def catalog(_bound_catalog: None) -> Catalog:
    return VcmiCatalog()


@pytest.fixture(scope="session")
def priors() -> Priors:
    return load_priors(SETTINGS.pp_dir)


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
    gameplay: GameplayStats

    def __call__(self, zone: OpenZone, seed: int, ledger: Ledger | None = None) -> PlacedZone:
        """Draw and place one zone of open land with no vegetation and a one-tile web at its
        top-left corner, outside any pipeline. Returns the placed zone."""
        ts, terrain, player = zone.ts, zone.terrain, zone.player
        w = max(x for x, _y in ts) + 1
        h = max(y for _x, y in ts) + 1
        tiles = frozenset(ts)
        st = self.gameplay[terrain]
        sz = SiteZone(terrain, st, tiles, frozenset(), frozenset({min(ts)}), tiles, tiles)
        lf = LevelField.build(0, [[int(Terrain.GRASS)] * w for _ in range(h)], [], lambda _o: True)
        site = ZoneSite(self.catalog, 1, sz, lf, seed)
        ledger = ledger or Ledger(set(BASIC_MINE_RES), 1, 0)
        spec = DrawSpec(1, terrain, len(ts), player=player)
        draw = ZoneDrawer(self.catalog, spec, site.st, ledger, seed).draw()
        place_town(site, draw, player)
        place_mines(site, draw, ledger, set())
        place_attractions(site, draw)
        tie_dwellings(self.catalog, site.objs)
        return site.placed()


@pytest.fixture
def open_zone(catalog: Catalog, priors: Priors) -> OpenZonePlacer:
    return OpenZonePlacer(catalog, priors.gameplay[0])
