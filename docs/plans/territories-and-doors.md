# Territories, Doors and Blocking Visits

Players on generated maps meet two defects that players on corpus maps never meet.

- A hero walks through signs and schools that VCMI blocks. On seed 25 at size 72, a road
  runs over the sign at 60,45. The School of Magic at 59,49 touches its neighbours only at
  a corner.
- Players reach each other in the first week without a fight. On seed 25, Red reaches
  Blue in 4 days. All four homes and two neutral towns share one unguarded stretch of
  about 1,000 tiles across seven zones.

A grill session settled the design below. The work lands in six slices, in order. Each
slice ends with `make check` green.

---

## Slice 0: drop the markov terrain model

The places model is the only terrain model. `MarkovTerrain`, the `NoContent` planner and
the `NoRoads` layer go, with the `--terrain` choice that selects them, their golden maps
and the tests that run them. The corpus Markov tables stay, because the places model's
accent paint and the underground's border texture read them. The macro zone growth stays,
because the underground grows its caves with it.

## Slice 1: one folder per map

`generate` writes every file of one map into `out/<name>/`.

- Without `--name`, the folder is `ppmap_s<seed>_<size>`, followed by the vegetation and
  terrain tags the stem carries today. Two sizes of one seed stop overwriting each other.
- With `--name`, the folder takes that name.
- `<name>.vmap` keeps its name, because `--install` copies the file as it is and VCMI lists
  the file name.
- `surface.png`, `underground.png` and `overlays.png`.
- `run.json`: the seed, the size and every flag, enough to rebuild the same map.
- `topology.json` arrives in slice 4.

A rerun empties the folder first, so no file from an earlier run survives.

Only `generate` moves. `render-vegetation`, `render-sprites` and the ontology render keep
their paths. The existing `out/vmap` and `out/render/pp` folders stay untouched. The README
and `generate_test.py` name the old paths and change in the same commit.

## Slice 2: named stacks count as guards, and `inspect`

`VcmiCatalog.creature_level` returns None for a fixed monster such as "12 Unicorns",
because its identity carries no subtype. The route reader, the effort map and the family
reader then ignore those guards, and the corpus hero-day priors undercount guards. The fix
reads the creature from the static type. The priors get re-mined and the golden hashes
refreshed in the same commit.

The same slice adds `inspect`, one subcommand for one map. It opens a `.vmap` from any
folder, a corpus map by name, or a seed and a size generated in memory with the
`generate` flags. Its views print what the shared readers compute, so corpus and generated
maps go through the same code.

- `tile x,y`: the terrain, the objects standing on or visiting the tile, whether it blocks,
  its place and its territory, and the guard that watches it.
- `near x,y`: every object within a radius, with its mask and visit tiles.
- `route a b`: the cheapest hero path between two tiles or two players, its hero-days, and
  every guard paid on the way.
- `territories` arrives in slice 4.

## Slice 3: lasting objects block their visit tile

VCMI blocks an object's visit tile. The model treats it as walkable. The fix closes the
visit tile of every object that lasts.

- The `Catalog` port gains `is_vanish`. A hand-kept list in the catalog's trait table
  names the types that vanish: resources, artifacts, scrolls, monsters, Pandora's boxes,
  quest guards, border guards, boats, the `removeObject` pickups and the scholar.
- The map's blocking view closes the visit tile of every object whose `is_vanish` is
  false. Placement, roads, routes, the snug test and the corpus readings all read that
  view. Routes keep the rule that a vanishing object is gone once taken, and a monster
  still costs its toll.
- The corpus readings switch with the generator. The snug, patch and flank priors get
  re-mined, and the golden hashes refreshed.
- Siting tries a snug spot first, then a spot with at least one closed side, then a
  smaller object. If none fits, it places nothing and warns. A corner contact alone never
  counts as a closed side. The "any spot" pass goes away.

## Slice 4: territories and doors

The map splits into territories. Each territory belongs to one player or is neutral.
Territories are built from whole zones, so a terrain accent inside a zone never moves a
territory edge.

### The corpus shape

Read on 262 levels of 159 corpus maps, as stretches a hero crosses without a fight:

| Measure | Corpus |
|---|---|
| Zones per player territory | 1 in 35%, 2 in 23%, 3 in 15%, more in 27% |
| Zones per neutral territory | 1 in 65%, 2 in 16%, 3 or more in 11% |
| Doors between two bordering territories | 1 in 80%, 2 in 17% |
| Door guard level out of a player territory | median 3, mostly 1 to 4 |
| Door guard level between neutral territories | a little stronger |
| Narrow borders with every crossing guarded | 60%, the territory edges |
| Narrow borders with no guard | 33%, the borders inside a territory |

Two player territories touch in the corpus, always through a guarded door.

### Drawing the partition

The places model draws territories on its early place graph, before zones grow.

- A player territory is the home plus a corpus-drawn number of its early-graph neighbours.
  The graph already keeps homes apart and forbids two homes a shared neighbour, so player
  territories never overlap.
- Neutral zones group on the early graph into territories sized from the corpus spread,
  mostly one or two zones.
- Once zones grow, a territory zone that touches no other zone of its territory becomes a
  neutral territory of its own.
- A pocket reached only through a player's territory stays neutral and gets no special
  rule. 82% of home-to-pocket borders are guarded in the corpus.

The underground has no homes and no early graph. Every underground territory is neutral.
Its zones group on the borders they share once grown, sized from the neutral corpus
spread, with the same one-tile doors guarded from the neutral table.

The terrain step publishes the partition for later steps, and `generate` writes it to
`topology.json` with the early graph and the planned doors.

### Border kinds

- Between territories, a spanning forest picks one door on enough edges to connect every
  territory. Extra doors follow at corpus odds.
- A second door goes on another zone border along the same territory edge. Without one, it
  goes on the same front when the passage planner finds room for two passages. Otherwise
  the pair gets one door.
- Every other border on a territory edge is walled.
- Inside a territory, a spanning forest keeps every zone linked through gated or open
  borders. The other inner borders keep the corpus draw, and none of them gets a guard.

A door is exactly one tile wide. Inner gated passages keep today's width of 3.

### Door guards

A new step runs right after vegetation and before gameplay. Mine pricing and the 14-day
mine rule then see the door tolls.

- Door guards form their own class, apart from prize guards.
- A door's level comes from a corpus table: one for doors out of a player territory, one
  for doors between neutral territories.
- A door into a sealed loot zone or a treasure zone gets no door guard. The gate or the
  treasure guard already holds it, and two guards would charge the player twice for one
  prize. The loot zones get chosen before the door step for that reason.

### Reading territories on both sides

A shared reader in `core/reading/` reads territories from any map. A new miner records the
corpus spread into the place statistics. `readings` compares zones per territory, doors
per pair and door levels between the corpus and generated maps. `inspect territories`
prints each territory's owner, size, zones and doors, with an ASCII map. It also lists
where the planned topology and the read topology disagree.

## Slice 5: the rival cut

Enemies sit at least a week apart: seven hero-days home to home on the effort map, guard
tolls included. Allies may meet earlier.

The door step runs the cut after drawing door levels. While an enemy pair is under seven
days, it raises the weakest door on their cheapest route by one level. When every door on
that route is at the top level, it warns and moves on.
