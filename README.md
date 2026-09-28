# vcmi-mapgen

Procedural map generation for [VCMI](https://vcmi.eu) (the open-source Heroes of
Might & Magic III engine), learned from a corpus of 159 real maps. It generates
**playable `.vmap` maps** — terrain, towns, mines, creature dwellings, guarded
treasure, vegetation — that you can open in the VCMI editor and play right away.

![Generated 72×72 island map](docs/img/pp-map-islands-s7.png)

*A 72×72 two-player island map generated from a single seed
(`cli.py generate --seed 7 --size 72 --water-mode islands --players 2`)
and rendered with the real H3 sprites, exactly as the VCMI editor shows it.*

The colored discs are the editor's genuine **random-object** sprites (random
monster / artifact / resource / town, by level band) — VCMI rolls them when the
game starts, so every playthrough of a generated map is different while the
economy and guard strength stay balanced.

![Detail: generated coastline with a random town, sawmill and guarded loot](docs/img/pp-map-islands-s7-detail.png)

## How it works

Everything is **learned from real maps** (`maps/`, 159 classic `.h3m` maps) and
**deterministic** (same seed ⇒ bit-identical map):

1. **Macro layout** — capacity-constrained zone growth with textured borders,
   optional ocean/islands, and an optional underground level connected by
   Subterranean Gate pairs.
2. **Terrain** — corpus-learned transition tiles (shores, terrain edges) so
   coastlines and terrain borders look hand-drawn.
3. **Towns and mines** — towns and mines placed with corpus-fitted densities;
   every town gets its sawmill and ore pit; gold mines scale with the number of
   towns; a protected walkable web guarantees every object stays reachable
   (validated, not hoped for).
4. **Vegetation** — a corpus-fitted Gibbs marked point process scatters trees,
   rocks and lakes with the same clustering statistics as the real maps.
5. **Attractions** — dwellings, banks and shrines settle next to the vegetation,
   on spots that keep the walkable field in one piece.
6. **Loot** — unguarded scatter along routes, guarded caches in pockets with a
   monster on the mouth; guard level scales with the guarded value.

## Requirements

- [`uv`](https://docs.astral.sh/uv/) — run everything through `uv run`; it
  resolves the environment (Pillow + numpy, the rest is stdlib).
- A local **VCMI install with the Heroes III data files** — used for sprite
  rendering and as the `.vmap` header template. The standard per-OS locations
  are auto-detected (Linux flatpak `~/.var/app/eu.vcmi.VCMI/data/vcmi`, Linux
  `~/.local/share/vcmi`, macOS `~/Library/Application Support/vcmi`, Windows
  `Documents/My Games/vcmi`); point the `VCMI_HOME` environment variable at the
  `vcmi` data directory if yours lives elsewhere.

## Generate maps

```bash
# One 72x72 two-player island map -> PNG render in out/render/pp/, playable
# .vmap in out/vmap/ (each player slot is wired to its own starting town, so
# the map is playable immediately — victory: defeat all)
uv run python -m vcmi_mapgen.cli generate \
    --seed 7 --size 72 --water-mode islands --players 2

# Two levels: surface + underground, linked by subterranean gates
uv run python -m vcmi_mapgen.cli generate \
    --seed 3 --size 72 --subterrain

# 4 players in two teams
uv run python -m vcmi_mapgen.cli generate \
    --seed 5 --size 108 --players 4 --teams 2v2
```

## Map

- `vcmi_mapgen/`: the Python package. It generates, renders and reads maps, and extracts the corpus.
- `vcmi-h3m-format-reference/`: verbatim VCMI C++ sources that document the `.h3m` format.
- `maps/`: the `.h3m` corpus of 159 real maps, the source data.
- `maps_vmap/`: one `.vmap` per corpus map, the generator's input, regenerable from `maps/`.
- `data/`: corpus-derived priors and fitted statistics.
- `docs/`: specs, architecture and the VCMI H3M format reference notes.

## Tests

```bash
uv run pytest
```

Covers the sprite renderer (all four H3 DEF formats, decode coverage, renderer
determinism), the point-process sampler (determinism, protected-web
legality), gameplay placement rules, and `.vmap` export contracts. Tests that
need the H3 data files skip when no VCMI install is present.
