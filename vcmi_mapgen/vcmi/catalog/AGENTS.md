# vcmi/catalog/: the object catalog

The single source of truth for objects. The core reaches it only through `VcmiCatalog`. Identity, footprint mask, terrain coupling and
decoration category come from `data/ontology/taxonomy.json` and
`data/ontology/leaf_meta.json`. `python -m vcmi_mapgen.cli regen-ontology` re-derives both
from the editor table `objects.txt`.
