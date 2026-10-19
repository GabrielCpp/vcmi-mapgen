# Planned territories: a top-down front as an alternative terrain generator

Disclosure: I read the existing solution before this note's order applied. That covers the
terrain front's code (`places.py` `surface`, `territories.py`, `homes.py`, `layout.py`), the
plan `docs/plans/territory-topology.md`, and the memories about territories. Its decisions
are listed as claims in 1b. The corpus arrangement measurements in 1 and 7 came from a
scratch extraction over the 159 corpus maps through the shared territory reader.

## 1. Problem

A player who opens a generated map sees territories that look like noise: thin strips one
tile wide, corridors that go nowhere and neighbours that touch by accident. A hand-made map
such as "All for One" reads as a composition. The homes sit on a ring, a neutral middle or
a band of home land joins them, and each territory's shape follows from its place in that
arrangement.

Done looks like this to the person who reviews maps:

- 5 surface PNGs from 5 seeds at 72 tiles, 2 players, generated with the new front, show
  territories arranged the way a corpus family arranges them. Homes sit near the rim,
  territories are compact blobs with organic borders, and no territory is a strip under
  3 tiles wide.
- The same 5 seeds with the default front stay byte-identical: the golden hashes hold.
- The full pipeline runs to the end on those 5 seeds with the new front, so the PNGs show
  vegetation and gameplay too.

Out of scope:

- Making the new front the default. This note builds a switchable prototype.
- The underground. It keeps today's front.
- Honouring the corpus plan's own door pairs. The prototype keeps today's door draw.
- Tuning the vegetation field or gameplay placement to the new shapes.
- More than one corpus plan blended into one map.

## 1b. Claims

1. "The front is top-down": territories first, then the places inside them
   (`docs/plans/territory-topology.md`).
2. Slice 4 of that plan grows the place shapes first, then picks homes among them, then
   groups places into territories (`places.py` `surface`).
3. The territory count and the home budget come from one corpus map near the player count
   and the land (`territory_record`).
4. A neutral territory too small to expect a prize joins its neighbour (`merge_dull`).
5. Doors come from a spanning forest over bordering territories plus detours above
   `MAX_HOP` (`draw_doors`).
6. Wall widths come from the hops between territories (`wall_depths`).
7. The terrain model is a role, `TerrainModel`, with one variant today.

## 2. Parts and concepts

### Level 1: parts

1. **The plan source.** It owns the arrangements hand-made maps use: where each territory
   sits in normalised map coordinates, its share of the territory area and its owner. It
   never knows the map being generated. It hands one arrangement to the planner.
2. **The planner.** It owns turning one arrangement into a plan for this map: which
   player gets which home, the symmetry applied, the jittered site and the area target of
   each territory. It never knows tiles. It hands the plan to the partitioner.
3. **The partitioner.** It owns assigning every land tile to one territory so each
   territory reaches its area target and stays one connected blob with an organic border.
   It never knows owners or the corpus. It hands the territory map to the subdivider.
4. **The subdivider.** It owns cutting each territory into places and choosing the home
   place and home point inside each home territory. It never knows how the territory map
   was drawn. It hands the places, the homes and the territory of each place to the rest
   of the front.
5. **The front assembler.** It owns choosing which way of drawing territories the map
   uses, and running the rest of the front (doors, water, roles, palette, paint) on the
   result. It never knows how either way works inside.

Flow: the assembler picks the planned way. The plan source gives one arrangement near the
player count and land. The planner fixes the symmetry, the players and the targets. The
partitioner fills the land. The subdivider cuts places and picks homes. The assembler then
runs doors, water, roles and painting on those places as it does for the existing way.

In plain words: borrow the layout of a real map, stretch it onto our land, grow each
territory from its marked spot until it has its share, then cut each territory into rooms.

### Level 2: concepts

**The plan source**

| Concept | Owns | Never knows |
|---|---|---|
| Territory plan | one corpus map's territories as sites, shares and owners | tiles of any map |
| Plan choice | drawing one plan near the player count and land | how a plan is applied |

**The planner**

| Concept | Owns | Never knows |
|---|---|---|
| Symmetry | one of the 8 square symmetries applied to the sites | the land |
| Site jitter | moving each site by a small seeded offset | the area targets |
| Seat assignment | which player takes which home territory | the sites' positions |
| Area target | each territory's tile budget from its share and the land | the partition method |

**The partitioner**

| Concept | Owns | Never knows |
|---|---|---|
| Site snap | moving each site onto the nearest land tile | the weights |
| Walking distance | the geodesic distance over land from each site | the area targets |
| Border noise | a smooth field, with a wavelength that scales with the side, added to the score | the sites |
| Quota flood | growing all territories in turn from their sites until each holds its target | the noise |
| Blob repair | reassigning every piece cut off from its site to the neighbour it borders most | why a piece was cut off |

**The subdivider**

| Concept | Owns | Never knows |
|---|---|---|
| Place growth | cutting one territory's tiles into places, its place count from its area | other territories |
| Home seat | the home point and home place inside a home territory, where a town room fits | the partition |

**The front assembler**

| Concept | Owns | Never knows |
|---|---|---|
| Territory front (role) | land, players, seed and priors in; places, homes, territory per place and the record out | which variant answers |
| Shapes-first variant | today's way: shapes, then homes, then territories | the planned variant |
| Planned variant | plan, partition, subdivide | the shapes-first variant |
| Front choice | picking the variant by name for the map | either variant's inside |

Shared value types: the land mask, the place layout, the homes and the territory record.
The corpus priors are the read-only reference.

## 3. Invariants

1. Every land tile belongs to exactly one territory. Owner: blob repair. The power weights
   uphold it.
2. Each territory is one 4-connected piece holding its site. Owner: blob repair.
3. Each place lies inside one territory. Owner: place growth.
4. Each player has exactly one home place, in its own territory, with a town room on land.
   Owner: home seat.
5. The same seed and options give the same map. Owner: the planned variant. Every concept
   draws from a seeded stream named after it.
6. The default front's output does not change. Owner: the golden check.

## 4. Forces and patterns

Forces:

- F1. Two interchangeable ways of drawing territories must both run, chosen per map, and
  compared on the same seeds.
- F2. The rest of the front (doors, water, roles, paint) must not care which way drew the
  territories.
- F3. The corpus is the only source of arrangements, and the core cannot read the corpus.
- F4. The partition must stay cheap at 144 tiles: the speed target is about 60 s CPU per
  map and is met with little margin.
- F5. Area targets vary per territory, from 2 % to 30 % of the land.

Patterns between parts:

- Strategy behind a role (F1, F2): the territory front is a role with two variants. The
  choice sits where the steps are assembled, by a name from the CLI. The existing way
  becomes the shapes-first variant, not a base class.
- One value handed along (F2): both variants hand back the same value, so the rest of the
  front stays one sequence of plain functions.
- Port on the priors (F3): a miner reads the plans from the corpus into a priors file. The
  core reads only the frozen priors.

Patterns inside parts:

- Walking distance is computed once per site (F4). Only the weights iterate, so the
  20 rounds cost 20 array argmins, not 20 flood fills.
- Power weights (F5): an additively weighted Voronoi on squared walking distance, with
  weights nudged by the area error each round. It is the one formula that meets unequal
  area targets and keeps cells compact.
- Every other concept is a plain function.

Claims:

1. Re-derived. Territories first is the direct answer to the problem: shape follows place
   in the arrangement.
2. Rejected for this variant. It is what produces the noise shapes. It stays as the
   shapes-first variant.
3. Re-derived in part. The plan choice draws one corpus map near the player count and
   land, and now takes its whole arrangement, not only its count.
4. Kept downstream, unchanged. The planned variant should seldom produce a dull neutral,
   because shares come from a real map.
5. Kept, unchanged (out of scope in 1).
6. Kept, unchanged.
7. Re-derived, with a narrower role. The variation is in the territory front only, not
   in the whole terrain model. A second terrain model would duplicate the palette, water
   and painting.

SOLID check:

- Single responsibility: each Owns reads without "and". Seat assignment and area target
  were split for that reason.
- Open/closed: a third way of drawing territories adds one variant and one name in the
  choice.
- Liskov: each variant is a kind of the territory front only.
- Interface segregation: the role has one call, the one the front makes.
- Dependency inversion: the rest of the front names neither variant.

Open lookups:

- L1. Does the territory reader give each corpus territory's tiles, so a miner can compute
  centroids and shares? It decides whether a new reader is needed.
- L2. Can the shape grower run on one territory's mask with its own cap list? It decides
  whether place growth is new code.
- L3. Where does the front take the player count and the water style, and does a new
  option reach it without touching every caller? It decides the choice's home.

## 5. Mapping onto the existing system

Revision log:

- R1 (2, the planner). The plan holds only territories with a single owner and drops maps
  where several players share a territory. Finding: 28 of 159 corpus maps share a home
  territory, and the seat assignment needs one territory per player.
- R2 (2, plan choice). Plan choice draws among maps whose single-owner home count equals
  the player count. Finding: 2 players have 23 such maps and 4 players have 41, enough to
  draw from.

Parts:

- The plan source: **New**. Miner in `corpus/mine/territories.py` beside
  `mine_territories`, value type in `core/priors/territories.py`, data in
  `data/pp/territory_stats.json`. L1 resolved: `read_territories` returns `labels` per tile
  and each territory's owners, so centroids and shares come from it.
- The planner and the partitioner: **New**, in a new `core/steps/terrain_gen/planned.py`.
  The partition math is a grid algorithm and goes to `core/grid/quota.py`.
- The subdivider: **Reshape**. `grow_shapes(land, caps, rng)` in `shapes.py` grows on any
  land mask, so it runs once per territory mask (L2 resolved). `choose_homes` picks among
  all places map-wide by gap, which is the wrong job here. The home seat is new code that
  reuses `room_tiles` and `room_side` from `homes.py`.
- The front assembler: **Reshape**. `surface` in `places.py:134` inlines the shapes-first
  way in lines 147 to 161. That block becomes the shapes-first variant, and `surface`
  calls the role instead.

Concepts:

- Territory front (role): **New**, a `Protocol` in `terrain_gen/model.py` beside
  `TerrainModel`. It returns a value holding the `Layout`, the `Homes`, the territory of
  each place and the `TerritoryCount` record that `surface` reads later for the floor.
- Shapes-first variant: **Exists** inline, extracted unchanged so the golden hashes hold.
- Front choice: **Reshape**. `build_steps` in `cli/steps.py:86` builds
  `PlacesTerrain(SURFACE_FORMS[...])`. `PlacesTerrain` takes the front as a second
  argument. `StepConfig` gains `front: str = "shapes"`, and `generate` gains
  `--front shapes|planned`. L3 resolved: `TerrainOptions` does not need to change.
- Territory plan, plan choice: **New**. `TerritoryStats` gains
  `plans_by_map: tuple[TerritoryPlan, ...]`. Each plan holds its `TerritoryCount` record,
  so the record and the arrangement come from the same map.
- Walking distance: **Exists** in spirit in `core/grid/` geodesic paths. The partition
  needs a full distance field per site, a BFS over the land mask in numpy.
- Border noise: **Exists**, `core/grid/` noise.
- Blob repair: **New**. `settle` in `territories.py:213` splits a territory into pieces
  and drops the owner of the piece without a home, which keeps the piece as a neutral
  territory. Blob repair instead hands the piece to a neighbour, so it is new.

What the existing system has that the design lacks:

- `home_budget` and `target_gap`: waste for the planned variant. The plan's shares and
  ring positions replace them.
- `shape_caps`: a concept the design missed. It sets the map's place count from the corpus
  place stats. The subdivider uses it and splits the caps across territories by area.
- `merge_dull` and `draw_doors` downstream in `bordered`: kept. `bordered` takes the
  drawn territories through `Front.drawn` and the planned variant fills it.

## 5b. What must not move

| Receiver | Gets today | Enforced by | Before | Holds when |
|---|---|---|---|---|
| Every user of the default front | byte-identical maps per seed | `make golden` | golden.json at b9e4960 | unchanged |
| The test suite | green | `make check` | 908 passed | all pass |
| A player on the planned front | a playable map end to end | the pipeline's own errors | default front: seeds 1 to 10 at 72 finish (A9) | 5 of 5 seeds finish |
| A player on the planned front | rooms in the vegetation | nothing | default: room_count median 11.5, room_largest 0.029 at 72 | reported, not held |
| The map reviewer | generation time | nothing | 96.5 s seed 3 at 144, single run | planned front within 10 % at 144 |
| A player on the planned front | basic mines within 14 days | gameplay breach lines | default: reported per seed | reported, not held |

The prototype reports the rows marked "reported, not held". The design lets them move
because the prototype is for judging shapes. Section 1 lists tuning as out of scope.

## 6. Slices

1. **Planned shapes on screen.** Miner and plan prior, planner, partitioner, subdivider,
   role with both variants, `--front` option. Done when 5 seeds (1 to 5) at 72 with
   2 players run end to end with `--front planned` and their surface PNGs exist. The golden
   hashes and `make check` hold. Each 5b row is reported with its after-value.
2. **Planned doors.** The plan's door pairs feed `draw_doors` as preferred pairs. Done when
   the planned front's homes are door-disconnected at the corpus rate. Not in this
   prototype.

## 7. Assumptions

1. **Assumption**: a corpus territory's centroid and area share describe its place in the
   arrangement well enough, even though the territory reader covers only part of the land
   (All for One's territories hold about 1000 of 5184 tiles).
   **Decided**: shares are normalised over the territory area, and the partition fills all
   the land.
   **Basis**: the family maps from the scratch extraction read as the real layouts.
   **If wrong**: territory plan, area target.
2. **Assumption**: squared walking distance minus a weight gives compact connected cells
   in almost every case, and blob repair handles the rest.
   **Decided**: blob repair runs once after the weights settle.
   **Basis**: none for geodesic power diagrams on this land. A guess from the Euclidean case.
   **If wrong**: blob repair becomes a constraint inside the weight loop.
3. **Assumption**: 20 weight rounds bring every territory within 10 % of its target.
   **Decided**: fixed 20 rounds, step from the area error.
   **Basis**: none. Measured in slice 1.
   **If wrong**: power weights.
4. **Assumption**: land is square and the corpus plans normalise onto it by the side.
   **Decided**: sites map from [0, 1]² by the side.
   **Basis**: every corpus map and every generated map is square.
   **If wrong**: symmetry, site snap.
5. **Assumption**: the shape grower on a small territory mask returns at least one place.
   **Decided**: each territory gets at least one cap.
   **Basis**: `grow_shapes` takes any land mask.
   **If wrong**: place growth.
6. **Assumption**: the water forms flood on the planned territories as they do on today's.
   **Decided**: the water form is unchanged.
   **Basis**: `Shore` takes the layout and territories, whoever drew them.
   **If wrong**: the front assembler.
7. **Assumption**: border noise amplitude of a third of the mean site spacing, with a
   wavelength of a sixth of the side, makes organic borders without strips.
   **Decided**: those values.
   **Basis**: none. A guess, judged on the PNGs.
   **If wrong**: border noise.
8. **Assumption**: 5 PNGs at 72 and 2 players show the shapes well enough for a verdict.
   **Decided**: seeds 1 to 5, size 72, 2 players.
   **Basis**: the user asked for 5 PNGs.
   **If wrong**: slice 1's done-when.
9. **Assumption**: seeds 1 to 5 at 72 finish on the default front.
   **Decided**: those seeds.
   **Basis**: the A measurements ran seeds 1 to 10 at 72 to the end.
   **If wrong**: pick the next seeds that finish on the default front.
