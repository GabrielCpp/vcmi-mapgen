from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.vcmi.terrain import BY_PREFIX, TERRAINS, name_of, prefix_of


def test_every_terrain_has_one_code_prefix_and_name() -> None:
    assert set(TERRAINS) == set(Terrain)
    assert all(c.code == t.value for t, c in TERRAINS.items())
    assert len(BY_PREFIX) == len(Terrain)


def test_rock_decodes_from_its_vcmi_prefix() -> None:
    assert BY_PREFIX["rc"] is Terrain.ROCK
    assert prefix_of(9) == "rc"
    assert name_of(6) == "subterr"
    assert name_of(11) == ""


def test_barriers_are_water_and_rock() -> None:
    assert [t for t in Terrain if t.is_barrier] == [Terrain.WATER, Terrain.ROCK]
    assert Terrain.WATER.is_water and not Terrain.ROCK.is_water
