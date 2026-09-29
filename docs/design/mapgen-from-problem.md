# Map generator, designed from the problem

Sections 1 to 4 were written from the problem statement and the root `AGENTS.md` alone.
No source, test, data or `docs/` file was open before section 4 was finished. Two things
sat in context before the design started: the root `AGENTS.md` module list, and a one-line
memory note saying gameplay is placed after vegetation. Each concept below passed the test
"would I have named this without having seen the code?". The ordering of vegetation before
gameplay objects is derived in section 4 from the back-contact measure, not taken from the
memory note.

Three lookups in section 5 changed a concept: L1 (Object Catalog now owns value), L3 (the
Walkable Web reroutes instead of reserving tiles) and the segmentation finding under Zone
Layout. L6 changed a pattern: the run gains a per-stage snapshot. Writing section 5 also
split F4 into F4 (speed) and F12 (stable draws). Sections 2 to 4 carry those changes, and
section 5 says where each came from.

## 1. Problem

A VCMI player who wants a fresh map each session gets a generated map that gives itself
away at a glance: objects sit alone in bare clearings, forests look like noise, and zones
look like blobs. A mapmaker's map does not, but it costs days.

Done, as the player and the reviewer see it:

- The VCMI editor opens every generated map without errors, and a two-player game starts.
- A reviewer who sets a generated render beside corpus renders cannot pick it out by bare
  clearings, uniform forests or blob zones.
- For each object type, depth from the zone edge, walking distance to the nearest passage,
  openness around the visitable tile and back contact with impassable ground all fall
  within the corpus spread.
- A developer changes one part of generation and sees the result in under 20 seconds at
  size 72.

Out of scope:

- Victory conditions other than "defeat all".
- Timed events, scripts and quests.
- Editing or extending an existing map.
- Balancing guard strength for play beyond "strength tracks value".
- Map templates chosen by the user, such as a fixed zone count or a named layout.

## 2. Concepts

| Concept | Owns | Never knows |
|---|---|---|
| Map Request | The seed, size and level flag that name one map | How any stage uses them |
| Random Stream | The draws one stage makes, derived from the request and the stage's name | What the stage draws for |
| Object Catalog | What an object type is: identity, footprint, visitable tiles, allowed terrain, value | How often the corpus places it |
| Corpus Map | One real map read from `.h3m` into the same shape a generated map has | Statistics over the corpus |
| Placement Measure | One number that describes where a placed object sits on a map | Whether the map is real or generated |
| Corpus Priors | The corpus spread of counts and measures per object type and terrain | What an object type is (Object Catalog) |
| Zone Layout | Which zone owns each tile, found by one segmentation of the terrain that runs on real and generated maps alike | Objects |
| Passage | A crossable stretch of shared border between two zones | What guards it (Guard) |
| Terrain | The terrain type of each tile | Which frame a tile shows (Tile Appearance) |
| Tile Appearance | The frame each tile shows, given its neighbours | Why a tile has its terrain type |
| Walkable Web | A connected set of passable tiles that links every start town, passage and visitable tile, rerouted when a cut lands on it | Which object stands where |
| Vegetation | Where trees, mountains and rocks stand, in each terrain's texture | Gameplay objects |
| Player Setup | Player slots, teams, start zones and the victory condition | Tiles |
| Object Quota | How many objects of each type a zone receives | Where they go |
| Site Rules | Whether one object of one family may stand on one tile | How good that tile is (Site Choice) |
| Site Choice | Picking the best legal tile for one object | Why a tile is legal (Site Rules) |
| Guard | The monster strength that stands in front of a guarded value | Where the value came from |
| Map | The tile grid and the object list of one map | How the map was generated |
| Map Export | The `.vmap` bytes VCMI opens | How the map was generated |
| Map Picture | The PNG drawn with the game's sprites | How the map was generated |
| Realism Verdict | Whether a set of measured values falls inside the corpus spread | How the values were measured |
| Generation Run | The order of the stages and where to stop | What a stage does inside |

Flow:

1. Corpus Map reads each `.h3m`. Placement Measure runs over each one, and Corpus Priors
   stores the spread, keyed by Object Catalog identities.
2. Generation Run takes a Map Request and hands each stage its Random Stream.
3. Terrain lays out each level's terrain from Corpus Priors. Zone Layout segments it into
   zones, the same way Corpus Priors segmented the real maps. Passage picks the crossable
   stretches of each shared border.
4. Player Setup assigns a start zone per player. Walkable Web lays a connected set of
   tiles through start sites and passages.
5. Vegetation fills the land in the terrain's texture and leaves the web open.
6. Object Quota sets each zone's counts from Corpus Priors. For each object, Site Rules
   filters the candidate tiles, and Site Choice scores the survivors with Placement
   Measure against Corpus Priors. The Map takes the object. Walkable Web reroutes around
   the object's blocking tiles and extends to its visitable tile.
7. Guard sizes a monster for each guarded passage, mine and treasure from the value the
   Object Catalog gives. Pickups follow the same path as other objects.
8. Tile Appearance fixes frames from the corpus frame statistics. Map Export writes the
   `.vmap`, and Map Picture writes the PNG.
9. Realism Verdict runs Placement Measure over generated maps and compares with Corpus
   Priors.

## 3. Invariants

| Invariant | Enforced by |
|---|---|
| An object's identity, footprint, visitable tiles and allowed terrain come only from the game's object table | Object Catalog |
| Corpus Priors carries counts and spreads keyed by identity, never a footprint or a terrain rule | Corpus Priors |
| Every object stands on terrain its type allows | Map, on insertion |
| No object covers another object's visitable tile | Map, on insertion |
| No blocking cut splits the web: after every placement the web still connects every start town to every passage and every visitable tile, with guard tiles counted as passable | Walkable Web |
| A zone is found by the same segmentation on a real map and a generated one | Zone Layout |
| Guard strength reads the guarded value from one table | Object Catalog |
| Every passage is a wide stretch of shared border and carries exactly one guard | Passage |
| Guard strength rises with the value behind it | Guard |
| Each player has one start town, in a zone of its own | Player Setup |
| Every random draw comes from a stream the run derived from the request | Generation Run |
| The exported bytes depend only on the Map | Map Export |
| A measure gives the same number for the same placement on a real map and a generated one | Placement Measure |

## 4. Forces and patterns

Forces:

- F1. The game's object table and the corpus change independently. A catalog regeneration
  must not require a corpus re-extraction, and the reverse.
- F2. Corpus Priors come from 159 maps. Deriving them is expensive, and they rarely change.
- F3. The same four measures must mean the same thing on real and generated maps. The
  "done" check compares them, so a drift between two implementations fakes a pass. Depth
  and passage distance are measured inside a zone, so the zone definition is part of the
  measure too.
- F4. A developer changes one stage and must see the result in under 20 seconds at size
  72.
- F12. Changing one stage must not reshuffle the draws of any other stage, or a
  before-and-after comparison shows noise instead of the change.
- F5. Placement legality has several rules, and some belong to one family: shipyards need
  a coast, gates need a matching tile on both levels, towns need room.
- F6. A site's quality combines four independent measures, each scored against its own
  corpus spread.
- F7. Object families grow over time. Gates and shipyards are recent examples of a family
  arriving with its own site rule.
- F8. The sprite archives exist only on machines with a VCMI install.
- F9. Forest texture varies by terrain type, and the variation is data from the corpus.
- F10. The request has validity rules: allowed sizes, and a level flag.
- F11. Vegetation must exist before objects are sited, because back contact with
  impassable ground can only be measured when the impassable ground is there.

Patterns:

| Concept | Pattern | Force |
|---|---|---|
| Map Request | Value object that validates on construction | F10 |
| Random Stream | Plain function from request, stage name and key to a seeded generator | F12 |
| Object Catalog | Plain value type, loaded from the editor table | F1 (kept apart from priors; no variation of its own) |
| Corpus Map | Adapter that yields a Map | F3 (measures read one type) |
| Placement Measure | Dict of named measure functions, shared by corpus and generated sides | F3 |
| Corpus Priors | Cache stored as data, keyed by corpus and measure version | F2 |
| Zone Layout | Plain function, shared by the corpus side and the generated side | F3 |
| Terrain, Passage | Plain functions inside their stage | none |
| Tile Appearance | Plain function | none |
| Walkable Web | Plain value type: a tile set with a connectivity check and a reroute | none |
| Vegetation | Plain function, parameterised by per-terrain texture data | F9 |
| Player Setup | Plain value type | none |
| Object Quota | Plain function of zone area and corpus rate | none |
| Site Rules | Universal rules as one function, plus a dict of extra predicates keyed by family | F5, F7 |
| Site Choice | Weighted sum of term functions, one term per measure | F6 |
| Guard | Plain function of value | none |
| Map | Plain type that checks its two insertion invariants | none |
| Map Export | Plain function over the Map | none |
| Map Picture | Plain function, sprite archive passed in | F8 (tests skip, so no port) |
| Realism Verdict | Oracle: measure, reference, tolerance and verdict as separate parts | F3 |
| Generation Run | Pipeline of stages with typed outputs and stop-after. After L6, also a snapshot of the map after each stage, keyed by the request and the upstream stages' versions, so a change to a late stage reruns only that stage | F4, F11 |

Open lookups:

- L1. Does the game's object table carry an object value? Guard's input source waits on
  it.
- L2. Do the corpus statistics and any generated-side measure share one implementation?
  The Placement Measure verdict waits on it.
- L3. Does the map type check terrain, visitable cover and reserved tiles on insertion?
  The three Map invariants wait on it.
- L4. Is there one random generator threaded through, or one per stage? Random Stream
  waits on it.
- L5. In what order do vegetation and gameplay placement run today? F11 waits on it.
- L6. How long does a size 72 run take, and which stage dominates? Whether F4 needs a
  cache beyond Corpus Priors waits on it.
- L7. Does `.vmap` store each tile's frame, or does VCMI derive it? Whether Tile
  Appearance sits on the export path waits on it.
- L8. Where does a passage's width come from? Passage's invariant waits on it.

## 5. Mapping onto the code

### Lookups

- L1. VCMI's own object config carries an `rmg.value` per object (seen in the flatpak
  install's `config/objects/*.json`). The ontology does not read it. Mine guards come
  from a hand table (`MINE_GUARD_LVL` in `steps/gameplay/mines.py`), and entrance guards
  from zone area (`steps/border/entrances.py`). This moved value into Object Catalog in
  section 2.
- L2. No. Three places measure placement, and they disagree on where. The gameplay
  priors in `steps/gameplay/mines.py` measure at the object's anchor, its bottom-right
  mask cell. The report in `corpus_match.py` measures at the entrance tile. Openness has
  two definitions: `mines.openness` over the zone's open set, and `corpus_match._window`
  over the zone minus vegetation. Only back contact is shared (`site.back_score`).
- L3. `MapState.add_objs` checks terrain (through `TerrainGate`) and visitable cover.
  It has no reserved tiles. The web lives in `ZoneWorkspace.prot`, and
  `steps/gameplay/site.py` lets a blocking cell land on it, then mends the web around the
  cut (`mend`, `reach_without`). That design is better than a fixed reserved set: a town
  can press into the web the way hand-made towns press into forest, and connectivity
  still holds. The concept was wrong, so section 2 now says the web reroutes, and the
  reserved-tile invariant is gone from section 3.
- L4. Each stage builds its own `random.Random(seed ^ salt ^ key * prime)`, in about
  twenty places. The draws are independent in spirit, but two sites build the same
  expression: `steps/gated/placer.py:327` and `steps/treasure/fill.py:284` both use
  `seed ^ (zid * 92821) ^ 0xA117`, so a zone's gated placer and its treasure fill draw
  the same numbers.
- L5. Vegetation runs before every gameplay object (`cli._generate_steps`). F11 holds.
- L6. A size 72 run takes 88 seconds. Stopping after segmentation still takes 43. A
  profile of the terrain stage shows the corpus read 477 times (159 maps, three passes)
  to relearn the autotiler (37 s under the profiler) and the terrain Markov chain (23 s)
  on every run. The stages after segmentation take about 45 seconds between them, so
  caching those two priors alone does not reach 20. This added the per-stage snapshot to
  Generation Run in section 4.
- L7. `.vmap` stores each tile's frame (`kit/vmap/terrain.py`), and the frames come from
  an autotiler learned from the corpus (`kit/tiling.py`). Tile Appearance sits on the
  export path and reads Corpus Priors.
- L8. A passage is `ENTRANCE_W = 3` front tiles per side, a constant in
  `kit/topology.py`, not a corpus draw.

### Measured today

`corpus_match` over seeds 1, 2 and 3 at size 72 compares corpus means with generated
means, measured at the entrance tile:

| Measure | Corpus mean across types | Generated mean across types |
|---|---|---|
| Depth from zone edge | 1.8 to 3.6 | 2.2 to 4.4 |
| Walking distance to a passage | 16.4 to 19.5 | 6.2 to 8.7 (shipyards 15.5) |
| Openness, 5 by 5 window | 9.9 to 15.3 | 13.1 to 19.1 |
| Back contact | 1.3 to 4.1 | 1.1 to 4.9 (dwellings 1.3 against 2.2) |

Generated objects sit two to three times closer to a passage than corpus objects, and in
more open ground. Part of the passage gap may come from zone size: corpus maps are mostly
larger than 72. A per-type spread comparison, not a mean, would settle it, and slice 1
builds that. Per-zone object counts fall inside the corpus p10 to p90 band in 30 of 31
generated zones, but the generated rate runs at 2.2 to 3.0 objects per 100 tiles against
2.5 to 3.5 in the corpus. No generated map placed a land transport object (the corpus has
1382).

### Verdicts

| Concept | Verdict | Where, and the mismatch |
|---|---|---|
| Map Request | Reshape | `cli.Args`. Nothing validates the size. The seed reaches each step by constructor instead of through a stream. The request also carries players, teams and water mode, which the problem does not name. The code is right to carry them. |
| Random Stream | Reshape | Ad hoc XOR salts in each module, with one collision (L4). The code is wrong. |
| Object Catalog | Reshape | `ontology.py` owns identity, footprint, visitable tiles and terrain as the concept says. It lacks value (L1). The code is wrong. |
| Corpus Map | Reshape | `kit/objects.load_faithful` yields a `FaithfulMap`, not a `MapState`. Measures bridge the two through a bare `(grid, objs)` pair, which works. The cost is the repeated read (L6), which belongs to Corpus Priors. |
| Placement Measure | Reshape | Three implementations measured at two different points (L2). The site chooser fits to one measure and the done-check reads another. The code is wrong, and this is the finding that matters most for the reviewer. |
| Corpus Priors | Reshape | `data/pp/*.json` caches gameplay, vegetation, gate and macro statistics with a version. The terrain Markov chain and the autotiler are relearned every run (L6). The code is wrong. |
| Zone Layout | Exists | `kit/segmentation.segment_level` over `kit/terrain_segment.segment`, used by `SegmentStep` and by every corpus pass. My first draft painted terrain per zone. The code derives zones from terrain, which keeps generated zones and corpus zones the same kind of thing (F3). The concept was wrong, and section 2 changed. |
| Passage | Reshape | `kit/topology.plan_entrances` plans them, `steps/border/entrances.py` guards "most" of them, and `BorderStep` seals the rest of each border. Width is a constant (L8). Not every passage carries a guard. The code is wrong on both, against the problem's "a monster guards it". |
| Terrain | Exists | `steps/terrain_gen/` (`macro_topo.py`, `markov.py`). `TerrainStep` also runs the autotiler, but the two stay separate functions. |
| Tile Appearance | Exists | `kit/tiling.py`. Its cost is Corpus Priors' finding. |
| Walkable Web | Reshape | Built in `steps/zone_plan.py`, mended in `steps/gameplay/site.py`, stored as tile sets in `ZoneWorkspace` inside the shared `PlacementWorkspace`. No stage checks whole-map reachability at the end: `kit/reachability.py` has no importer, and `PortalStep` rescues zones the web failed to reach. The concept is right, and the code spreads it over three places. |
| Vegetation | Reshape | `steps/vegetation/`, a corpus-fitted point process per terrain, as the concept says. `VegetationStep` also builds the zone plan, the web, the sea plan and the player zones' town room. The code is wrong to host them in this step. |
| Player Setup | Reshape | Split three ways: `GameplayStep._pick_player_zones` picks the largest zones, `zone_plan.py` keeps town room, and `VmapRenderer` applies slots, teams and the victory condition. The code is wrong: export should serialize a setup the map already holds. |
| Object Quota | Exists | `steps/gameplay/draw.py` draws one total per zone at the corpus rate and splits it by the corpus mix. |
| Site Rules | Reshape | Universal rules in `steps/gate/gates.fits` and `ZoneSite.fit`, family rules as flags inside `ZoneSite.fit` (`mine=`), plus `shipyards.py` and `gate_pairs.py`. Works, but a new family edits `ZoneSite`. Minor. |
| Site Choice | Reshape | `ZoneSite.intensity_order` samples tiles from a log-linear fit of depth, passage distance and openness. `ZoneSite.place` then takes the legal tile with the highest back contact in a 7 by 7 window. Back contact is maximised, not scored against its corpus spread, so it can overshoot the spread. The concept holds. |
| Guard | Reshape | Hand tables by mine subtype and by zone area (L1). The problem says strength tracks value. The code is wrong. `MINE_GUARD_LVL` also guards every mine, against the corpus rate of 64%. See decision 1. |
| Map | Exists | `models/map_state.py`. `add_objs` enforces both insertion invariants. |
| Map Export | Reshape | `renderers/vmap.py` and `kit/vmap/writer.py`. `zipfile.writestr` with a bare name stamps each entry with the wall clock, so two runs of the same seed give different bytes. The content is deterministic and the file is not. The code is wrong against a hard guarantee. It also applies teams (see Player Setup). |
| Map Picture | Exists | `renderers/png.py` and `renderers/sprites.py`, with the archive found per OS or through `VCMI_HOME`. |
| Realism Verdict | Reshape | `corpus_match.py` prints corpus and generated means side by side and a zone-count band. It gives no verdict per type and measure against the corpus spread, and it measures at a different point than the priors (L2). |
| Generation Run | Reshape | `pipeline.Pipeline` with `cli._generate_steps` and `--stop-after`. Three hand-written step lists exist: the CLI's, `corpus_match.generate` and the test fixture `steps_write_map_test.pipeline_steps`. No snapshot exists (L6). |

The code also holds stages the design has no concept for: gated zones behind a Border
Gate or monolith pair (`GatedStep`, `TreasureStep`), portal rescue (`PortalStep`), and
seer-hut quests with pocket caches (`LootStep`). Quests are out of scope in the problem.
Portal rescue exists because the web does not guarantee reachability upstream. Gated
zones and pocket caches may be mapmaker conventions the problem statement did not list.
Decision 6 covers them.

## 6. Slices

1. **The reviewer reads a verdict.** One Placement Measure per measure, taken at the
   visitable tile, shared by the priors builder and the report. Realism Verdict prints,
   per object type and measure, the corpus p10 to p90 and whether generated values fall
   inside. The gameplay priors are rebuilt with the shared measure. Concepts: Placement
   Measure, Corpus Priors, Realism Verdict. Done when the report and the priors call the
   same function, and the report prints an in or out verdict per type and measure.
2. **The same seed gives the same file.** Map Export writes zip entries with a fixed
   timestamp. A test runs the pipeline twice at a small size and compares file bytes.
   Concepts: Map Export, Generation Run. Done when the test passes on two runs a second
   apart.
3. **A late-stage change shows in under 20 seconds.** Corpus Priors caches the terrain
   chain and the autotiler. Generation Run snapshots the map after each stage and
   reloads it when the request and upstream versions match. Concepts: Corpus Priors,
   Generation Run. Done when a change to the gameplay stage reruns at size 72 in under 20
   seconds, and a cold run is timed and recorded.
4. **Guards track value.** Object Catalog reads `rmg.value`. Guard sizes mine, treasure
   and passage guards from it. Every passage carries a guard. Concepts: Object Catalog,
   Guard, Passage. Done when guard strength rises with value across a seed sweep, and
   every passage has a guard.
5. **Stages stop sharing draws.** Random Stream derives each generator from the seed, the
   stage name and a key through a hash. Concepts: Random Stream, Generation Run. Done when
   no two call sites can build the same stream, and the byte test from slice 2 has a new
   golden.
6. **The whole map is proven walkable.** A reachability check runs at the end of the run
   from every start town, through guards, to every visitable tile. Concepts: Walkable
   Web. Done when the check runs in the seed sweep and fails a map with a sealed object.
   Whether portal rescue can then go is decision 6.

## 7. Open decisions

1. **Mine guard rate.** The code guards every mine, a rule from an earlier bug report.
   The problem lists 64% as a hand-made convention. Recommendation: draw the rate from
   the corpus and always guard the rare mines. Reason: the problem statement is the newer
   and more explicit source, and the old bug was mines left entirely unguarded.
2. **Passage width.** The code uses 3 tiles. Recommendation: draw it from the corpus
   spread of open border per passage. Reason: the problem names wide passages as a
   hand-made convention, and the corpus is the source for how things are laid out.
3. **How to reach 20 seconds.** Options: snapshot after each stage, or make the late
   stages faster. Recommendation: cache the two terrain priors first, time again, then
   add the snapshot. Reason: the priors cache is cheap and certain, and the snapshot adds
   a staleness risk worth taking only if it is still needed.
4. **Guard value source.** Recommendation: read `rmg.value` from VCMI's config through
   the ontology. Reason: the problem gives the game's table authority over what an object
   is, and value is a property of the object.
5. **Where the web and player setup live.** Both now sit inside `VegetationStep` and the
   shared `PlacementWorkspace`. Recommendation: give each its own stage output and park
   the restructure under `target-architecture`. Reason: the change crosses every
   placement step and is larger than this note.
6. **Stages without a concept.** Gated zones, portal rescue, seer-hut quests and pocket
   caches. Recommendation: keep gated zones and pocket caches if the corpus shows them as
   conventions, drop seer-hut quests as out of scope, and retire portal rescue once slice
   6 proves reachability upstream. Reason: each should trace to the problem or go.
7. **Parked: stale architecture doc.** `docs/architecture.md` describes a retired
   segment, record and replay design and names modules that no longer exist
   (`zone_engine.py`, `render_editor.py`, `faithful.py`). Recommendation: rewrite or
   delete it under `target-architecture`. Reason: it loads the next reader with a design
   the code abandoned.
8. **Parked: dead reachability module.** `kit/reachability.py` has no importer, and its
   docstring points at a `ralph/verify.sh` that does not exist. Recommendation: fold it
   into slice 6 or delete it. Reason: slice 6 needs exactly this check.
