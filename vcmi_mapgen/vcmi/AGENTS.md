# vcmi/: Heroes III as VCMI sees it

Code here knows the game and its files. It knows nothing about the generator.

## Map

- `catalog/`: the object catalog: identity, footprint masks, terrain coupling and decoration category, read from `data/ontology/*.json`.
- `config.py`: `VcmiConfig`, the `(objectClass, objectSubID)` to VCMI `type::subtype` lookup read from the config directories of a `VcmiInstall`.
- `export.py`: `build_document`, the one translation from a `MapState` to a writable `VmapDocument`. It resolves each object's type and subtype from its kind and writes its payload through `options_of`.
- `footprint.py`: the mask charset. `footprint_of` decodes B/X/A/V rows into a core `Footprint`, and `mask_rows` encodes one back.
- `formats/`: the `.vmap`, `.h3m`, LOD, DEF and relaxed-JSON codecs.
- `install.py`: `VcmiInstall` and `find_install`, which finds the install from the environment and platform it is handed.
- `load.py`: `load_map`, the one translation from a `.vmap` file to a `MapState`. It re-derives each footprint from the ontology by animation.
- `options.py`: `options_of`, which turns a core payload into VCMI object options, with the town spells, the town options and the rewardable shapes.
- `players.py`: `parse_teams` and `apply_playability`, which set player slots, teams, town owners and victory on the header.
- `terrain.py`: each core `Terrain` with its Heroes III code, VCMI tile prefix and name, and `name_of` for a terrain code.
