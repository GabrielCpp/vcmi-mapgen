# vcmi/: Heroes III as VCMI sees it

Code here knows the game and its files. It knows nothing about the generator.

## Map

- `catalog/`: the object catalog: identity, footprint masks, terrain coupling and decoration category, read from `data/ontology/*.json`.
- `config.py`: `VcmiConfig`, the `(objectClass, objectSubID)` to VCMI `type::subtype` lookup read from the config directories of a `VcmiInstall`.
- `formats/`: the `.vmap`, `.h3m`, LOD, DEF and relaxed-JSON codecs.
- `install.py`: `VcmiInstall` and `find_install`, which finds the install from the environment and platform it is handed.
- `terrain.py`: each core `Terrain` with its Heroes III code, VCMI tile prefix and name, and `name_of` for a terrain code.
