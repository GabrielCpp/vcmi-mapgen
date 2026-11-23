from collections.abc import Callable

import pytest

from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import PlacedObject
from vcmi_mapgen.core.model.purpose import Purpose

type TownAt = Callable[[int, int], PlacedObject]


@pytest.fixture
def town_at(catalog: Catalog) -> TownAt:
    ident = catalog.candidates(Purpose.TOWN, "grass")[0]

    def build(x: int, y: int) -> PlacedObject:
        return PlacedObject(x, y, 0, Purpose.TOWN, ident.kind, ident.footprint)

    return build
