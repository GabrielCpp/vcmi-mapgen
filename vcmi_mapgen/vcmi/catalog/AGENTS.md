# vcmi/catalog/: the object catalog

The single source of truth for objects. The core reaches it only through `VcmiCatalog`. Identity, footprint mask, terrain coupling and
decoration category come from `data/ontology/taxonomy.json` and
`data/ontology/leaf_meta.json`. `python -m vcmi_mapgen.cli regen-ontology` re-derives both
from the editor table `objects.txt`.

## Map

- `adapter.py`: `VcmiCatalog`, the production implementation of the core's `Catalog` port. The pipeline hands it to every step, and its methods delegate to `objects` and `decor`. It also answers the role queries: guards, random artifacts, towns, dwellings and resources, portals, border gates, the subterranean gate, quest givers and spell scrolls. `types_with` answers which object types carry a core `Trait`.
- `decor.py`: decoration pools, vegetation categories, `pick`, `decode_identity` and the category by terrain matrix.
- `objects.py`: the per-object queries: `identity_of`, `mask_of`, `is_blocking`, `terrains_of`, `purpose_of_type`, the gameplay pools and the monster, spell and artifact accessors.
- `objects_test.py`: the catalog tests.
- `regen.py`: `regenerate`, which derives the taxonomy and leaf tables from `objects.txt` and the type table from VCMI's config, and writes all three.
- `roles.py`: the animations behind the object roles the catalog answers: random classes, portals, border gates, the subterranean gate and the spell scroll, and `TRAIT_TYPES`, the object types behind each `Trait`.
- `tables.py`: the fixed name tables, `LEAF_TERRAINS`, and the cached `taxonomy()`, `leaf_meta()` and `vcmi_type_classes()` loaders.
