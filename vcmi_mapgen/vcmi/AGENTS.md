# vcmi/: Heroes III as VCMI sees it

Code here knows the game and its files. It knows nothing about the generator.

## Map

- `catalog/`: the object catalog: identity, footprint masks, terrain coupling and decoration category, read from `data/ontology/*.json`.
- `content/`: the content setting. `manifest.py` `read_manifests` reads every installed `mod.json` with its submods, and `enabled.py` `enable` resolves a `ContentSetting` of named mods and banned names into the `EnabledSet` the catalog filters by. A named mod pulls in its dependencies, a submod joins when its own dependencies are enabled, and a conflict or a missing mod raises. `archive.py` reads a mod's files from its content folder or zip through the `ContentArchive` role. `objects.py` `mod_objects` reads each enabled mod's object configs into priced `ModObject` templates, with the purpose its handler gives. `mods.py` `load_mods` gathers them into the `ModContent` the catalog and the export share: the pools by purpose and terrain, the archives, and `requirement`, the header's mods list for the objects a map holds. A template whose animation the base game holds stays the base game's. `sprites.py` `SpriteSource` reads a sprite from the base game first, then from each mod's `sprites` folder.
- `config.py`: `VcmiConfig`, the `(objectClass, objectSubID)` to VCMI `type::subtype` lookup read from the config directories of a `VcmiInstall`.
- `export.py`: `build_document`, the one translation from a `MapState` to a writable `VmapDocument`, its terrain and roads among it. It resolves each object's type and subtype from its kind and writes its payload through `options_of`. A mod object keeps its mod's mask, and the header then requires its mod and the mod's parents.
- `footprint.py`: the mask charset. `footprint_of` decodes B/X/A/V rows into a core `Footprint`, and `mask_rows` encodes one back.
- `formats/`: the `.vmap`, `.h3m`, LOD, DEF and relaxed-JSON codecs.
- `install.py`: `VcmiInstall` and `find_install`, which finds the install from the environment and platform it is handed. `mods_dir` is the install's `Mods` folder.
- `load.py`: `load_map`, the one translation from a `.vmap` file to a `MapState`. It reads each tile's terrain and road type and re-derives each footprint from the ontology by animation.
- `options.py`: `options_of`, which turns a core payload into VCMI object options, with the town spells, the town options and the rewardable shapes.
- `players.py`: `parse_teams` and `apply_playability`, which set player slots, teams, town owners and victory on the header.
- `terrain.py`: each core `Terrain` with its Heroes III code, VCMI tile prefix and name, and `name_of` for a terrain code.
- `tiles.py`: the tile art: `Cell`, `TilerTables`, `tile` and `tile_strings`, which pick each tile's frame and flip from the tiler tables and each road tile's road type, frame and flip from its road neighbours, the tile-string codec, and `THIN_DRAWABLE`, the terrains that draw a strip one tile wide.
