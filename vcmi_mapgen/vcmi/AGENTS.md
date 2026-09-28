# vcmi/: Heroes III as VCMI sees it

Code here knows the game and its files. It knows nothing about the generator.

## Map

- `config.py`: `VcmiConfig`, the `(objectClass, objectSubID)` to VCMI `type::subtype` lookup read from the config directories of a `VcmiInstall`.
- `formats/`: the `.vmap`, `.h3m`, LOD, DEF and relaxed-JSON codecs.
- `install.py`: `VcmiInstall` and `find_install`, which finds the install from the environment and platform it is handed.
