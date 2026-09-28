"""The ``Ontology`` facade the pipeline holds: one object over the catalog modules."""

from collections.abc import Iterable, Iterator
from random import Random

from vcmi_mapgen.core.model import Identity, Mask
from vcmi_mapgen.vcmi.catalog import decor as DC
from vcmi_mapgen.vcmi.catalog import objects as OB
from vcmi_mapgen.vcmi.catalog.tables import ClassInfo, Taxonomy


class Ontology:
    """Object-facts facade: the abstraction layer between raw game data and the
    pipeline. Every ``PipelineStep``'s ``run(ontology, map_state)`` receives ONE shared
    instance of this class (see ``core/pipeline.py``) so a step never needs to hardcode an
    object's identity/mask/terrain coupling — it asks the ontology instead. Each method
    just delegates to the catalog module's accessor of the same name; the class
    exists so the pipeline holds and passes a single object, not the bare module."""

    def cluster_of(self, purpose: str, name: str | None = None, type_: str | None = None) -> str:
        return OB.cluster_of(purpose, name=name, type_=type_)

    def name_of(self, cid: int) -> str:
        return OB.name_of(cid)

    def resolve(self, cid: int, subclass: int) -> ClassInfo:
        return OB.resolve(cid, subclass)

    def build_tree(self) -> Taxonomy:
        return OB.build_tree()

    def iter_leaves(
        self, tree: Taxonomy | None = None
    ) -> Iterator[tuple[str, str, str, str, str, str]]:
        return OB.iter_leaves(tree)

    def has_animation(self, animation: str) -> bool:
        return OB.has_animation(animation)

    def mask_of(self, animation: str) -> Mask:
        return OB.mask_of(animation)

    def vmap_mask_of(self, animation: str) -> Mask | None:
        return OB.vmap_mask_of(animation)

    def cls_sub_of(self, animation: str) -> tuple[int, int] | tuple[None, None]:
        return OB.cls_sub_of(animation)

    def is_blocking(self, animation: str) -> bool:
        return OB.is_blocking(animation)

    def footprint_size(self, animation: str) -> int:
        return OB.footprint_size(animation)

    def identity_of(self, animation: str) -> Identity:
        return OB.identity_of(animation)

    def terrains_of(self, animation: str) -> set[str]:
        return OB.terrains_of(animation)

    def allowed_on(self, animation: str, terrain: str | int) -> bool:
        return OB.allowed_on(animation, terrain)

    def pool(
        self,
        object_class: str,
        terrain: str | int,
        *,
        blocking: bool | None = None,
        max_cells: int | None = None,
        exclude_types: Iterable[str] = (),
    ) -> list[Identity]:
        return DC.pool(
            object_class,
            terrain,
            blocking=blocking,
            max_cells=max_cells,
            exclude_types=exclude_types,
        )

    def pick(self, object_class: str, terrain: str | int, rng: Random) -> Identity | None:
        return DC.pick(object_class, terrain, rng)

    def decor_pool(
        self,
        terrain: str | int,
        *,
        blocking: bool | None = None,
        max_cells: int | None = None,
        exclude_types: Iterable[str] = (),
    ) -> list[Identity]:
        return DC.decor_pool(
            terrain, blocking=blocking, max_cells=max_cells, exclude_types=exclude_types
        )

    def gameplay_pool(self, terrain: str | int, purpose: str) -> list[Identity]:
        return OB.gameplay_pool(terrain, purpose)

    def mines_by_resource(self, terrain: str | int) -> dict[str, list[Identity]]:
        return OB.mines_by_resource(terrain)

    def visitable_purposes(self) -> tuple[str, ...]:
        return OB.visitable_purposes()

    def veg_categories(self) -> list[str]:
        return DC.veg_categories()

    def category_of(self, animation: str) -> int | None:
        return DC.category_of(animation)

    def decode_identity(
        self, category: int | str | None, terrain: str | int, rng: Random | None = None
    ) -> Identity | None:
        return DC.decode_identity(category, terrain, rng=rng)

    def category_terrain_matrix(self) -> list[list[bool]]:
        return DC.category_terrain_matrix()
