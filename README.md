# vcmi-mapgen

Procedural map generation for [VCMI](https://vcmi.eu) (the open-source Heroes of
Might & Magic III engine), learned from a corpus of 159 real maps. It generates
**playable `.vmap` maps** — terrain, towns, mines, creature dwellings, guarded
treasure, vegetation — that you can open in the VCMI editor and play right away.

![Generated 72×72 island map](docs/img/pp-map-islands-s7.png)

*A 72×72 two-player island map generated from a single seed
(`cli generate --seed 7 --size 72 --water-mode islands --players 2`)
and rendered with the real H3 sprites, exactly as the VCMI editor shows it.*

The colored discs are the editor's genuine **random-object** sprites (random
monster / artifact / resource / town, by level band) — VCMI rolls them when the
game starts, so every playthrough of a generated map is different while the
economy and guard strength stay balanced.

![Detail: generated coastline with a random town, sawmill and guarded loot](docs/img/pp-map-islands-s7-detail.png)

## How it works

Everything is **learned from real maps** (`data/corpus/h3m/`, 159 classic `.h3m` maps) and
**deterministic** (same seed ⇒ bit-identical map):

1. **Places.** A place graph drawn from corpus statistics, laid out on land:
   one home per player, treasure grounds and pockets, each with its hop count
   from the nearest home. Each border between two places is closed, gated or
   open. Ocean, islands and an underground level linked by Subterranean Gate
   pairs are optional.
2. **Terrain.** Each palette region of places takes one dominant terrain, and
   corpus-learned transition bands and accents paint it so coastlines and
   terrain borders look hand-drawn.
3. **Vegetation.** A cellular field covered with corpus-weighted trees, rocks
   and lakes. The `--vegetation gibbs` option uses a corpus-fitted Gibbs marked
   point process instead. A protected walkable web keeps every planned passage
   reachable.
4. **Gameplay.** Gates, towns, mines, shipyards, dwellings, banks and shrines
   settle with their backs against the vegetation. The whole map holds objects
   at the corpus rate per tile, and `--density` scales it. Every player reaches
   a mine of each basic resource within 14 hero-days. Each kind of object sits
   at the corpus effort from home, and the players reach the same count of it
   band by band, within one or two. Reward value and guard level follow each
   place's hop count from home.
5. **Loot.** Unguarded scatter along routes, and guarded caches in pockets with a
   monster on the mouth. Guard level scales with the guarded value.
6. **Roads.** Roads link the towns through the planned passages.

## Requirements

- [`uv`](https://docs.astral.sh/uv/) — run everything through `uv run`; it
  resolves the environment (Pillow + numpy, the rest is stdlib).
- A local **VCMI install with the Heroes III data files** — used for sprite
  rendering and as the `.vmap` header template. The standard per-OS locations
  are auto-detected (Linux flatpak `~/.var/app/eu.vcmi.VCMI/data/vcmi`, Linux
  `~/.local/share/vcmi`, macOS `~/Library/Application Support/vcmi`, Windows
  `Documents/My Games/vcmi`); point the `VCMI_HOME` environment variable at the
  `vcmi` data directory if yours lives elsewhere.
  A command that needs the install and finds none stops with a message
  naming `VCMI_HOME`.

## Generate maps

```bash
# One 72x72 two-player island map -> out/ppmap_s7_72/ holds the playable
# ppmap_s7_72.vmap, surface.png, overlays.png and run.json (each player slot is
# wired to its own starting town, so the map is playable immediately — victory:
# defeat all)
uv run python -m vcmi_mapgen.cli generate \
    --seed 7 --size 72 --water-mode islands --players 2

# Two levels: surface + underground, linked by subterranean gates; the folder
# also holds underground.png
uv run python -m vcmi_mapgen.cli generate \
    --seed 3 --size 72 --subterrain

# 4 players in two teams
uv run python -m vcmi_mapgen.cli generate \
    --seed 5 --size 108 --players 4 --teams 2v2

# Named "Twin Lakes", written to out/Twin Lakes/ and copied into the VCMI
# install's Maps/pp-gen/ folder, so it shows in the game's map list
uv run python -m vcmi_mapgen.cli generate \
    --seed 9 --size 72 --name "Twin Lakes" --install
```

`generate` empties the map's folder before it writes, so a rerun leaves no file from an
earlier run. `run.json` records the seed, the size and every flag of the run.

`generate` reads its corpus statistics from `data/pp/` and never loads a corpus map. After a
change to `data/corpus/vmap/` or to a statistic's code, rebuild the files:

```bash
uv run python -m vcmi_mapgen.cli mine-stats
uv run python -m vcmi_mapgen.cli mine-stats --only markov tiler
```

A missing file stops `generate` with an error that names `mine-stats`.

Four corpus tools run through the same CLI:

```bash
uv run python -m vcmi_mapgen.cli audit
uv run python -m vcmi_mapgen.cli extract-vmap
uv run python -m vcmi_mapgen.cli corpus-match --seeds 1 2 3 --size 48
uv run python -m vcmi_mapgen.cli readings --seeds 1 2 3 4 5 6 7 8 9 10 --size 72
```

`audit` lists the corpus objects the generator cannot reproduce, and exits non-zero when there
is one. `--densities` prints the per-terrain gameplay densities instead. `extract-vmap` rebuilds
`data/corpus/vmap/` from `data/corpus/h3m/`. `corpus-match` compares where gameplay
objects sit in corpus zones and in generated zones. `readings` generates maps and prints
the map-math 8 readings beside the corpus median and quartiles.

`inspect` prints what the readers see on one map. The map is a `.vmap` from any folder
(`--vmap`), a corpus map by name (`--corpus`), or a seed generated in memory with the
`generate` flags (`--seed`), which writes no file.

```bash
# The terrain, objects, place and guard of one tile, and whether a hero may stand on it
uv run python -m vcmi_mapgen.cli inspect --corpus "All for One" tile 23,8

# Every object within 4 tiles, with its mask and its visit tiles
uv run python -m vcmi_mapgen.cli inspect --vmap "out/Twin Lakes/Twin Lakes.vmap" near 30,30 --radius 4

# The cheapest hero route from Red's home town to Blue's, its hero-days and every
# guard on the way; --verbose lists the tiles
uv run python -m vcmi_mapgen.cli inspect --seed 25 --size 72 route P0 P1 --verbose
```

A route end is a tile `x,y` or a player `P0`, `P1` and so on, which stands for that
player's home town. `--level 1` reads the underground.

## Map

- `vcmi_mapgen/`: the Python package. It generates, renders and reads maps, and extracts the corpus.
- `vcmi-h3m-format-reference/`: verbatim VCMI C++ sources that document the `.h3m` format.
- `data/`: every map and data file the project keeps.
- `data/corpus/h3m/`: the `.h3m` corpus of 159 real maps, the source data.
- `data/corpus/vmap/`: one `.vmap` per corpus map, regenerable from `data/corpus/h3m/`.
- `data/catalog/`: the VCMI object tables, written by `cli regen-ontology`.
- `data/pp/`: corpus-derived priors and fitted statistics, written by `cli mine-stats`.
- `data/golden.json`: the golden map hashes.
- `docs/`: specs, architecture and the VCMI H3M format reference notes.

## Tests

```bash
uv run pytest
```

Covers the sprite renderer (all four H3 DEF formats, decode coverage, renderer
determinism), the point-process sampler (determinism, protected-web
legality), gameplay placement rules, and `.vmap` export contracts. Tests that
need the H3 data files skip when no VCMI install is present.
