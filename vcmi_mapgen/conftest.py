import random
from collections.abc import Iterator
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from pathlib import Path

import pytest

from vcmi_mapgen.cli.settings import Settings, load_settings
from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import MapState, Tile
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.placement.site import LevelField, PlacedZone, SiteZone, ZoneSite
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.priors.effort import EffortPriors
from vcmi_mapgen.core.priors.gameplay import GameplayStats
from vcmi_mapgen.core.steps.gameplay.economy import tie_dwellings
from vcmi_mapgen.core.steps.gameplay.pick import Picker
from vcmi_mapgen.core.steps.gameplay.placer import Demand, Placement
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
    return load_priors(SETTINGS.pp_dir, SETTINGS.pockets_file)


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
    effort: EffortPriors

    def __call__(self, zone: OpenZone, seed: int) -> PlacedZone:
        """Place one zone of open land with no vegetation and a one-tile web at its top-left
        corner, outside any pipeline: a player town on the centroid when a player starts
        there, then the zone's share of the map-wide pass. Returns the placed zone."""
        ts, terrain, player = zone.ts, zone.terrain, zone.player
        w = max(x for x, _y in ts) + 1
        h = max(y for _x, y in ts) + 1
        tiles = frozenset(ts)
        st = self.gameplay[terrain]
        sz = SiteZone(terrain, st, tiles, frozenset(), frozenset({min(ts)}), tiles, tiles)
        lf = LevelField.build(0, [[int(Terrain.GRASS)] * w for _ in range(h)], [])
        site = ZoneSite(self.catalog, 1, sz, lf, seed)
        homes = []
        if player:
            ident = self.catalog.random_town()
            town = site.place(Purpose.TOWN, ident, site.centroid_order(ident))
            homes = [] if town is None else [town]
        rng = random.Random(seed)
        demand = Demand(0)
        placement = Placement(self.catalog, [site], self.effort, demand, rng)
        _ = placement.place(placement.plan(homes, [], []), Picker(self.catalog, rng), list)
        tie_dwellings(self.catalog, site.objs)
        return site.placed()


@pytest.fixture
def open_zone(catalog: Catalog, priors: Priors) -> OpenZonePlacer:
    return OpenZonePlacer(catalog, priors.gameplay[0], priors.effort)
