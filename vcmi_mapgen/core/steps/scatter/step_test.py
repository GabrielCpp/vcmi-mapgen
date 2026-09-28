"""ScatterStep run on a fake catalog: the step learns about objects only through the
catalog it is handed."""

import contextlib
import io
from typing import final

from vcmi_mapgen.core.catalog import ObjectSpec
from vcmi_mapgen.core.grid.segment import label_zones
from vcmi_mapgen.core.model import Footprint, Identity, MapState, Role, Zone
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.pipeline import (
    LevelWorkspace,
    PlacementWorkspace,
    ProviderRegistry,
    ZoneWorkspace,
)
from vcmi_mapgen.core.planning.zone_index import ZoneIndex, ZoneRecord
from vcmi_mapgen.core.steps import ScatterStep
from vcmi_mapgen.core.steps.terrain_gen.result import Segmentation

PILE = Identity("fakePile", "gold", "fake_pile", Footprint.one(Role.VISIT))


@final
class FakeCatalog:
    def __init__(self) -> None:
        self.asked: list[tuple[str, ...]] = []

    def terrain_name(self, terrain: int) -> str:
        self.asked.append(("terrain_name", str(terrain)))
        return "grass"

    def identity_of(self, animation: str) -> Identity:
        self.asked.append(("identity_of", animation))
        return Identity("fakeRandom", None, f"fake_{animation}", Footprint.one(Role.VISIT))

    def spec(self, kind: str) -> ObjectSpec | None:
        self.asked.append(("spec", kind))
        return None

    def allowed_on(self, animation: str, terrain: str | int) -> bool:
        self.asked.append(("allowed_on", animation, str(terrain)))
        return True

    def candidates(self, purpose: str, terrain: str | int) -> list[Identity]:
        self.asked.append(("candidates", purpose, str(terrain)))
        return [PILE] if purpose == Purpose.RESOURCE_PILE else []

    def decor(
        self, terrain: str | int, *, blocking: bool | None = None, max_cells: int | None = None
    ) -> list[Identity]:
        self.asked.append(("decor", str(terrain), str(blocking), str(max_cells)))
        return []

    def decor_categories(self) -> list[str]:
        return []

    def decor_category(self, animation: str) -> str | None:
        self.asked.append(("decor_category", animation))
        return None

    def mines_by_resource(self, terrain: str | int) -> dict[str, list[Identity]]:
        self.asked.append(("mines_by_resource", str(terrain)))
        return {}

    def spells(self, level: int) -> list[str]:
        self.asked.append(("spells", str(level)))
        return []


def test_scatter_step_places_only_what_the_fake_catalog_offers() -> None:
    ts = frozenset((x, y) for x in range(30) for y in range(24))
    zone = Zone(
        terrain_type=Terrain.GRASS,
        area=len(ts),
        centroid=(14.5, 11.5),
        tiles=sorted(ts),
        tiles_set=ts,
    )
    workspace = PlacementWorkspace()
    workspace.levels[0] = LevelWorkspace(
        zones={1: ZoneWorkspace(terrain="grass", ts=ts, ts_full=ts, open_set=ts, entrances=[])}
    )
    ctx = ProviderRegistry()
    ctx.provide(workspace)
    ctx.provide(
        ZoneIndex(zone_records={0: [ZoneRecord(1, "grass", ts, set(ts), set(ts), set(ts))]})
    )
    ctx.provide(Segmentation({0: {1: zone}}, {0: label_zones({1: zone})}))
    map_state = MapState(size=30)
    catalog = FakeCatalog()
    step = ScatterStep(seed=3, size=30)
    step.inject(ctx)
    with contextlib.redirect_stdout(io.StringIO()):
        step.run(catalog, map_state)

    assert map_state.objs
    assert {o.animation for o in map_state.objs} <= {PILE.animation, "fake_avtrndm0"}
    assert ("candidates", Purpose.RESOURCE_PILE, "grass") in catalog.asked
