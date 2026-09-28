from collections.abc import Iterator

import pytest

from vcmi_mapgen.cli.settings import load_settings
from vcmi_mapgen.core.catalog import Catalog
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
