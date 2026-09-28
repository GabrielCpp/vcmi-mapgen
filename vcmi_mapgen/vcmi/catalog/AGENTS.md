# vcmi/catalog/: the object catalog

The single source of truth for objects. Identity, footprint mask, terrain coupling and
decoration category come from `data/ontology/taxonomy.json` and
`data/ontology/leaf_meta.json`. `python -m vcmi_mapgen.cli regen-ontology` re-derives both
from the editor table `objects.txt`.

## Map

- `adapter.py`: `Ontology`, the instance the pipeline hands to every step. Its methods delegate to `objects` and `decor`.
- `decor.py`: decoration pools, vegetation categories, `pick`, `decode_identity` and the category by terrain matrix.
- `objects.py`: the per-object queries: `identity_of`, `mask_of`, `is_blocking`, `terrains_of`, the gameplay pools and the monster, spell and artifact accessors.
- `objects_test.py`: the catalog tests.
- `regen.py`: `regenerate`, which derives both tables from `objects.txt` and writes them.
- `tables.py`: the fixed name tables, `LEAF_TERRAINS`, and the cached `taxonomy()` and `leaf_meta()` loaders.
