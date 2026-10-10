"""ScatterStep run on a fake catalog: the step learns about objects only through the
catalog it is handed."""

import contextlib
import io
from typing import final

from vcmi_mapgen.core.catalog import Crossing, HeroPace, ObjectSpec, Trait
from vcmi_mapgen.core.grid.segment import label_zones
from vcmi_mapgen.core.model import Footprint, Identity, MapState, Role, Zone
from vcmi_mapgen.core.model.artifact import ArtifactSet, ArtifactTier
from vcmi_mapgen.core.model.purpose import Purpose
from vcmi_mapgen.core.model.terrain import Terrain
from vcmi_mapgen.core.pipeline import ProviderRegistry
from vcmi_mapgen.core.placement.site import PlacedZone
from vcmi_mapgen.core.planning.zone_index import ZoneIndex, ZoneRecord
from vcmi_mapgen.core.planning.zone_plan import PlanLevel, PlanZone, ZonePlan
from vcmi_mapgen.core.priors.bundle import Priors
from vcmi_mapgen.core.steps.gameplay.result import GameplayResult
from vcmi_mapgen.core.steps.scatter.step import ScatterStep
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

    def abandoned_mines(self, terrain: str | int) -> list[Identity]:
        self.asked.append(("abandoned_mines", str(terrain)))
        return []

    def types_with(self, trait: Trait) -> tuple[str, ...]:
        self.asked.append(("types_with", str(trait)))
        return ()

    def spells(self, level: int) -> list[str]:
        self.asked.append(("spells", str(level)))
        return []

    def artifacts(self, tier: ArtifactTier) -> list[str]:
        self.asked.append(("artifacts", tier))
        return []

    def artifact_sets(self) -> list[ArtifactSet]:
        self.asked.append(("artifact_sets",))
        return []

    def artifact(self, name: str) -> Identity | None:
        self.asked.append(("artifact", name))
        return None

    def monsters(self, level: int) -> list[str]:
        self.asked.append(("monsters", str(level)))
        return []

    def _role(self, *asked: str) -> Identity:
        self.asked.append(asked)
        return Identity("fakeRandom", None, "_".join(("fake", *asked)), Footprint.one(Role.VISIT))

    def creature_level(self, kind: str) -> int | None:
        self.asked.append(("creature_level", kind))
        return None

    def dwelling_level(self, kind: str) -> int | None:
        self.asked.append(("dwelling_level", kind))
        return None

    def guard(self, level: int) -> Identity:
        return self._role("guard", str(level))

    def random_artifact(self, tier: ArtifactTier) -> Identity:
        return self._role("random_artifact", str(tier))

    def random_resource(self) -> Identity:
        return self._role("random_resource")

    def random_town(self) -> Identity:
        return self._role("random_town")

    def random_dwelling(self, level: int | None) -> Identity:
        return self._role("random_dwelling", str(level))

    def portals(self) -> list[Identity]:
        return [self._role("portal")]

    def border_gates(self) -> list[tuple[Identity, Identity]]:
        return [(self._role("border_gate"), self._role("keymaster"))]

    def border_guards(self) -> list[tuple[Identity, Identity]]:
        return [(self._role("border_guard"), self._role("keymaster"))]

    def subterranean_gate(self) -> Identity:
        return self._role("subterranean_gate")

    def quest_givers(self, terrain: str | int) -> list[Identity]:
        self.asked.append(("quest_givers", str(terrain)))
        return []

    def spell_scroll(self, spell: str) -> Identity:
        return self._role("spell_scroll", spell)

    def thin_terrains(self) -> frozenset[Terrain]:
        self.asked.append(("thin_terrains",))
        return frozenset()

    def crossing(self, kind: str) -> tuple[Crossing, int] | None:
        self.asked.append(("crossing", kind))
        return None

    def is_vanish(self, kind: str) -> bool:
        self.asked.append(("is_vanish", kind))
        return kind == PILE.kind

    def pace(self) -> HeroPace:
        self.asked.append(("pace",))
        return HeroPace(land=1500, sea=1500, cost={})


def test_scatter_step_places_only_what_the_fake_catalog_offers(priors: Priors) -> None:
    ts = frozenset((x, y) for x in range(30) for y in range(24))
    zone = Zone(
        terrain_type=Terrain.GRASS,
        area=len(ts),
        centroid=(14.5, 11.5),
        tiles=sorted(ts),
        tiles_set=ts,
    )
    none = frozenset[tuple[int, int]]()
    plan_zone = PlanZone("grass", ts, (), none, none, none)
    ctx = ProviderRegistry()
    ctx.provide(ZonePlan({0: PlanLevel({1: plan_zone}, {})}, ()))
    ctx.provide(GameplayResult({0: {1: PlacedZone((), none, (), ts, ts, none)}}, {}, {}))
    ctx.provide(ZoneIndex(zone_records={0: [ZoneRecord(1, "grass", ts, ts, ts, ts)]}))
    ctx.provide(Segmentation({0: {1: zone}}, {0: label_zones({1: zone})}))
    map_state = MapState(size=30)
    catalog = FakeCatalog()
    step = ScatterStep(priors, 3, 30)
    step.inject(ctx)
    with contextlib.redirect_stdout(io.StringIO()):
        step.run(catalog, map_state)

    assert map_state.objs
    assert {o.kind for o in map_state.objs} <= {PILE.kind, "fake_random_resource"}
    assert ("candidates", Purpose.RESOURCE_PILE, "grass") in catalog.asked
