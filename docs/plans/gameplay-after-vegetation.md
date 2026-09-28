# Gameplay After Vegetation

Generated maps leave every gameplay object in its own bare pocket. Real maps do the
opposite. On the corpus, a town's body overlaps vegetation 92% of the time, a mine's 61%,
a dwelling's 55% and a bank's 45%. The visitable tile is covered under 0.4% of the time.
Today `TownsStep` places towns, mines, seals and shipyards before vegetation, and it
reserves a spot for every dwelling, bank and shrine. `VegetationStep` then forbids every
reserved tile, so the trees stop one tile short of each object.

Three objects on `out/render/pp/ppmap_s1*.png` (seed 1, 48x48) show the defect:

- The sulfur mine enters at 11,43. Its back would touch the forest at 12,42.
- The library enters at 45,35. Its back would touch the forest at 44,34.
- The subterranean gate enters at 11,36. It belongs about one tile up, against the trees.

A grill session settled the design below. This plan follows
`pipeline-refactor-v3-generic-pipeline.md`, whose step contract (`inject(ctx)` plus
`run(ontology, map_state)`) it keeps unchanged.

---

## Goals

1. Place every gameplay object after vegetation: gates, towns, mines, shipyards,
   dwellings, banks and shrines.
2. Put each object's back against tiles a hero cannot walk. The back is the top of the
   sprite, because the entrance is always in the bottom row.
3. Let blocking tiles stack on vegetation, never on another gameplay body.
4. Draw one object total per zone at the corpus rate, so small zones stop getting twice the
   corpus count.
5. Keep the spatial distribution the corpus shows: distance to the zone edge, distance to
   gates, openness around the entrance.
6. Keep the seed-sweep invariant: no step removes or moves an object an earlier step placed.

## Order inside `GameplayStep`

1. Gates, only when an underground level exists.
2. Towns.
3. The economy pair of mines.
4. The other mines.
5. Shipyards.
6. Dwellings, banks and shrines.

Guards and seals follow the object they belong to.

## Count per zone

Each zone draws one total at the corpus rate. The corpus holds about 3.1 to 3.5 gameplay
objects per 100 zone tiles in every size bucket. The median zone of 60 to 100 tiles holds
2 objects, and the median zone of 150 to 250 tiles holds 6.

The total is split by the corpus category mix. Forced objects count inside it:

- the player town
- the economy pair
- gates
- the shipyard that serves a water body

When forced objects exceed the total, the step places them anyway and the zone gets
nothing else. When a forced object finds no legal spot, the step skips it and logs a
warning. It never removes an earlier object to make room.

The current draw in `mines.py` (`_ZonePlacer._draw_counts`) rounds up per category through
`_stoch` and `scaled_cap`, and it adds the shipyard outside any budget. A 91-tile zone at
seed 10 received 5 objects, and a 70-tile zone received 4. The corpus median for both is 2.

## Legality

A spot is legal when all of these hold:

- The entrance tile and its approach are free and reachable from the zone's walkable web.
- No blocking tile lands on another gameplay body, a guard, a seal or a seaport cell.
- Blocking tiles may land on vegetation. The vegetation object underneath stays.
- The 2-tile gap between gameplay bodies stays. Trees may fill that gap.
- No footprint tile lands on the underground tunnel protect set.

## Back score

For each column of the sprite, take the topmost drawn tile of that column, overlay tiles
(`V`) included. Score one point for that tile and one for the tile above it, when a hero
cannot walk there. Unwalkable means trees, rock, water or outside the map.

- Front and flanks do not score.
- A 1-tile object has no back. Guards score zero.
- A gate sums its score over both levels.

## Spot choice

Corpus intensity picks a neighbourhood of about 3 tiles. Back contact picks the tile
inside it. This keeps the corpus spatial distribution and still pulls each object onto the
trees. The player town keeps its pull toward the zone centre.

## Vegetation changes

- `TownsStep` stops placing gameplay objects. It keeps segmentation bookkeeping,
  entrances, the ridge and the water population.
- The walkable web is built from zone entrances and gates only. Gameplay approaches no
  longer enter `protected_web` as `extra_nodes`.
- `_planned_tiles` and the planned forbid go away.
- `_attract` goes away, both the mine ring and the planned ring.
- The border bias (`rim8 - ent_bands - forbid`) stays.
- After placement, each object links its approach to the web, the way
  `attractions._path_to_web` does today.

## Mines and shipyards

- A mine's guard stays on the approach tile.
- A seal goes only on a side tile that is still open after vegetation.
- Shipyards take the same back score as the rest.
- Each water body still gets one shipyard, and it counts inside its zone's total.

## Stories

Each story ships a playable map and passes the full test suite.

### 1. Walking skeleton: attractions against the trees

Dwellings, banks and shrines stop reserving spots before vegetation.

- `mines.py` stops emitting `planned` for them. `ZoneWorkspace.planned` goes away.
- `VegetationStep` drops `_planned_tiles` and the planned ring from `_attract`.
- `TownsStep` drops their approaches from the web's `extra_nodes`.
- `attractions.py` replaces `_adjacency` with the back score, lets bodies land on
  vegetation, and keeps the web link.

Check: on seed 1 at size 48, the library sits with its back on the forest.

### 2. Zone totals at the corpus rate

- One draw per zone, split by the corpus mix, with forced objects inside it.
- The shipyard boost outside the budget goes away.
- Forced objects that exceed the total are placed, and nothing else is.

Check: a sweep over seeds 1 to 12 at size 48 lands each zone-size bucket within the corpus
p10 to p90 band.

### 3. Mines after vegetation

- The economy pair goes first, then the other mines.
- The guard stays on the approach. Seals go only on open side tiles.
- The mine ring in `_attract` goes away.

Check: on seed 1 at size 48, the sulfur mine enters at 12,42 or at another spot with its
back on trees.

### 4. Towns after vegetation

- The player town keeps its centre pull.
- The web is built from entrances and gates only.
- `TownsStep` still picks the player zones and provides `TownsIndex`.
- `GameplayStep` produces `town_of_zone` for `BorderStep`.

Check: the size 72 seed 1 case that had no fit spot in the pessimistic measurement places
its town.

### 5. Shipyards after vegetation

- `ensure_water_seaports` moves into `GameplayStep`.
- `seaport_blk` and `seaport_appr` are produced there for the later steps.

Check: every water body on the seed sweep keeps a shipyard.

### 6. Gates inside `GameplayStep`

- Gates are placed first, with the back score summed over both levels.
- `GateStep` leaves the pipeline.
- `GateResult` is still provided, for `GatedStep`, `BorderStep` and `PortalStep`.

Check: on seed 1 at size 48, the gate at 11,36 moves against the trees.

### 7. Corpus-match report

A report compares corpus and generated maps per object type on four measures:

- depth from the zone edge
- distance to the nearest gate
- openness around the entrance
- back contact

It starts as a script under `vcmi_mapgen/`. It becomes a test once the tolerances are
known.

## Tests affected

- `steps/gameplay/mines_test.py`
- `steps/gameplay/water_test.py`
- `steps/gate/gates_test.py`
- `steps/towns/step_test.py`
- `steps/vegetation/sample_test.py`
- `steps/gated/step_test.py`
- `steps/seed_sweep_test.py`
- `steps/steps_write_map_test.py`

## Measured risk

A measurement over 16 maps (12 seeds at size 48, 4 at size 72) counted legal spots per
moving object, about 1,200 objects in all.

- With vegetation only in the way, every object had at least one spot in its zone.
- With every other gameplay object placed first, 2 objects had no spot. One was a town in
  a 227-tile zone holding 10 other objects. One was a bank in a 91-tile zone holding 6.
- About 10 objects had no spot within 3 tiles of their corpus-intensity pick. They sat in
  zones of 70 to 174 tiles, or on the top map edge.

Both zero-spot cases are overfilled zones. Story 2 removes that overfill.

## Implementation notes

`TownsStep` is gone. `GameplayStep` picks the player zones, provides `TownsIndex` and
commits the sea objects. `VegetationStep` builds the zone plan first through
`steps/zone_plan.py`: entrances, the walkable web, the ridge, the planned sea objects and one
open shipyard landing per shore. Vegetation treats the planned sea objects as taken, so the
maps match the ones the two-step version drew.

The 2-tile gap is measured between blocking cells, not whole footprints. On the corpus,
73% of counted objects sit within 2 tiles of another object's footprint, and 80% keep 2
tiles between blocking cells.

A player town that finds no spot in its zone moves to the largest town-free zone that fits
it, then to a large zone that already holds a town. Towns go before mines, so the town gets
first pick of the ground. On seed 6 at size 48 the only large surface zone has no second
spot, and the map ends with one player town and a warning.

A dwelling, bank or visitable that finds no spot falls back to a smaller object of the same
purpose, the largest shape first. The zone total and the category mix hold.

The seed sweep over seeds 1 to 12 at size 48 with an underground level puts every bucket
median inside the corpus p10 to p90 band. 74 of 91 zones land inside the band:

| zone tiles | corpus p10/p50/p90 | generated p10/p50/p90 | in band |
|---|---|---|---|
| 20-60 | 0/1/3 | 0/1/5 | 18/20 |
| 60-100 | 1/2/5 | 0/1/2 | 14/17 |
| 100-150 | 2/4/7 | 1/3/4 | 13/15 |
| 150-250 | 3/6/9 | 2/4/7 | 7/10 |
| 250-500 | 5/11/19 | 5/9/11 | 4/4 |
| 500-1000 | 12/21/33 | 6/12/16 | 7/13 |
| 1000+ | 25/44/101 | 27/31/43 | 11/12 |

The 500-1000 bucket is mostly underground zones. Tunnel ground covers about half of each
underground level, and no footprint may land on it, so those zones place about half their
drawn total.

## Contracts that must not break

- `rebuild --identity --verify` prints `IDENTITY OK`. This plan touches only the
  procedural generator.
- No step removes or moves an earlier object (`seed_sweep_test.py`).
- Object identity, masks and categories come from `ontology.py`. The corpus supplies only
  rates, mixes and spatial statistics.
- Placement stays seeded and deterministic.

## Parked

- The eight carved underground gate sites from `terrain_gen/step.py` stay bare. Gates do
  not use them.
- The gate example coordinate "9,12" is unresolved. The plan assumes one tile up.
- The `vcmi-mapgen-pipeline` skill still describes the kwargs `inject` and
  `PipelineBuilder`. It needs its own update.
