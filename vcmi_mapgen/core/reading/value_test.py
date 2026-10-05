from vcmi_mapgen.core.catalog import Catalog
from vcmi_mapgen.core.model import PlacedObject
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.reading.value import ValueTable, value_of


def _dwelling(catalog: Catalog, kind: str) -> PlacedObject:
    return PlacedObject.at(catalog.identity_of(kind), (5, 5), purpose=Purpose.DWELLING)


def test_a_dwelling_is_worth_a_thousand_per_creature_level(catalog: Catalog) -> None:
    table = ValueTable.of(catalog)
    assert value_of(catalog, table, _dwelling(catalog, "avgazur")) == 10000
    assert value_of(catalog, table, _dwelling(catalog, "avgtrog0")) == 1000
    random3 = catalog.random_dwelling(3).kind
    assert value_of(catalog, table, _dwelling(catalog, random3)) == 3000
