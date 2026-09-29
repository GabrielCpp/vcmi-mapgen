# v3: random VCMI maps that read as hand-made, designed from the problem

## Disclosure

The problem statement is the input. It is a problem, not an as-built spec.

Before this skill loaded, the session context already held three descriptions of the
existing solution. I did not open them. They loaded on their own:

- The root `AGENTS.md`, with its module list: a step pipeline, a shared placement
  workspace, a terrain gate checked when objects are added, an ontology built from the
  editor table, a vegetation step that starts from zone entrances, a walkable web and a sea
  plan.
- A memory line: "all gameplay placed after vegetation, sprite top against trees,
  corpus-rate zone totals".
- The last five commit subjects, among them "place every gameplay object after vegetation",
  "keep room for player towns" and "draw the gate count and spacing from the corpus".

Section 1b lists the design decisions they carry as claims, so that section 4 must
re-derive or reject each one. Every part and concept below passed the test "would I have
named this without having seen the solution?". Two are close calls and say so in place.

## 1. Problem

A Heroes III player on VCMI wants a fresh map every session. A generated map arrives in
seconds, but the player spots it at a glance: objects sit alone in bare clearings, forests
look like noise and zones look like blobs.

Done, as the player and the developer see it:

- The VCMI editor opens every generated map without errors, and a two-player game starts on
  it.
- A reviewer who sets a generated render beside corpus renders cannot pick out the
  generated one by bare clearings, uniform forests or blob zones.
- For each object type, four placement measures fall inside the corpus spread: depth from
  the zone edge, walking distance to the nearest passage, openness around the visitable
  tile, and how much of the sprite's back touches impassable ground.
- The same seed, size and level flag give the same map, byte for byte.
- A developer changes one part and sees the result in under 20 seconds at size 72.

Out of scope:

- Victory conditions other than "defeat all".
- Timed events, scripts and quests.
- Editing or extending an existing map.
- Balance between players beyond "a guard's strength tracks the value behind it".
- User-authored zone templates of the kind VCMI's own generator takes.

## 1b. Claims

The input is a problem, so it carries no claims of its own. These come from the
preloaded context named in the disclosure, in its words.

1. All gameplay objects are placed after vegetation.
2. A sprite's top is placed against trees.
3. Zone object totals come from the corpus rate.
4. Generation is a pipeline of steps, and the placement steps share one workspace.
5. A terrain gate is checked whenever objects are added to the map.
6. One ontology, derived from the editor's object table, is the single source of truth
   for object identity, footprint, terrain and decoration category.
7. The gate count and spacing are drawn from the corpus.
8. Vegetation keeps room for player towns.
9. Vegetation starts from zone entrances, a walkable web and a sea plan.

## 2. Parts and concepts

### Level 1: parts

1. **Game rules.** What the game says an object and a terrain are.
   - Owns: object identity, footprint, visitable tiles, allowed terrain, value, and how
     terrain tiles join their neighbours.
   - Never knows: the corpus, or any particular map.
   - Hands: a read-only catalog that every other part consults.
2. **Mapmaking conventions.** What human-made maps look like, learned from the 159 real
   maps.
   - Owns: the measures taken on a map, and their spread across the corpus: densities,
     guard rates, overlap rates, placement measures, passage widths and vegetation texture
     per terrain.
   - Never knows: what an object is. It keys everything by the catalog's identities. It
     also never knows how the generator uses a norm.
   - Hands: norms to Land layout, Scenery and Settlement. Hands the measuring itself to
     Playtest.
3. **Land layout.** The shape of the world before anything stands on it.
   - Owns: levels, zones with irregular borders and a terrain each, seas and lakes, which
     zones connect, the passages that realise each connection, and each player's home zone.
   - Never knows: individual trees or objects.
   - Hands: a land plan to Scenery and Settlement.
4. **Scenery.** Dressing the land with trees, mountains and rocks. The problem calls it
   vegetation. I name it Scenery to keep clear of an existing step's name.
   - Owns: where each decoration stands, the texture of stands and clearings, the walls
     along zone borders, and the open ground a hero walks on.
   - Never knows: which gameplay object will stand where.
   - Hands: dressed land to Settlement.
5. **Settlement.** Everything a hero visits or fights.
   - Owns: towns, mines, dwellings, banks, shrines and other visitables, pickups, gates
     between levels, monolith pairs, shipyards, and the guards and border gates in front of
     passages and treasure.
   - Never knows: how the vegetation texture was made. It reads only which tiles are open.
   - Hands: the finished map to Playtest.
6. **Playtest.** The checks a mapmaker runs before release.
   - Owns: reachability from every start, and the comparison of the finished map against
     the corpus norms.
   - Never knows: how any part built what it checks.
   - Hands: a verdict and a report to Publishing and to the developer.
7. **Publishing.** Turning the map into what a player or a reviewer opens.
   - Owns: player slots, teams and the victory condition, the `.vmap` file, the PNG
     drawn with the game's sprites, and the developer's overlays on that PNG.
   - Never knows: how the map was generated.
   - Hands: files on disk.

Flow: the seed, the size and the level flag enter Land layout. Land layout hands a land
plan to Scenery. Scenery hands dressed land to Settlement. Settlement hands the finished
map to Playtest, and Playtest's pass lets Publishing write the files. Game rules and
Mapmaking conventions sit beside the flow. Every part reads them, and they read nothing
from the flow. The conventions are learned once from the corpus and stored. A generation
run reads the stored norms and never reads the corpus.

In plain words: the generator knows the game's rules and has studied how real mapmakers
work. It sketches the land, plants the forests and hills, then settles towns, mines and
treasure with guards where a mapmaker would put them. It walks the map like a player to
check that everything can be reached, and saves a file the game opens plus a picture.

Test of the split:

- The paragraph above uses no technical vocabulary.
- A tile-by-tile imperative generator fits it. So does a constraint solver that places
  scenery and settlement from one model, as long as the solver keeps them as two passes.
- No part is named after an existing stage. Scenery is the close call and says why above.

### Level 2: concepts

Two shared value types cross parts. They belong to no part:

- **Map draft**: the tile grid with its terrain and the list of placed objects. Land
  layout creates it, and every later part adds to it. The corpus reader produces the same
  type, so one measure applies to both.
- **Seed stream**: the source of every random draw. Each part draws from its own named
  child stream.

#### 1. Game rules

| Concept | Owns | Never knows |
|---|---|---|
| Object kind | What an object is: its class, its subtype, and whether it is a random class | How often a kind occurs, which is a convention |
| Footprint | Which tiles an object blocks and which tile a hero visits | Where the object stands |
| Terrain allowance | Which terrains an object may stand on | Which terrain a zone has |
| Terrain kind | Whether a terrain is land, water or rock, and whether it is passable | Zones and objects |
| Tile join | Which terrain image a tile shows given its neighbours | Why the terrain is there |
| Worth | The value of a treasure and the strength of a monster, on one scale | Where either stands |

Six concepts. The catalog is a read-only reference every part consults.

#### 2. Mapmaking conventions

| Concept | Owns | Never knows |
|---|---|---|
| Corpus | Reading the 159 real maps into map drafts | Any statistic |
| Survey | The measures of one map draft: placement measures, overlap, density, passage width | Whether the map is real or generated |
| Norm | The spread of each measure across the corpus, keyed by object kind and terrain | How a part draws from it |
| Texture sample | How stands and clearings of one terrain are arranged | The zone the texture will fill |

Four concepts. Survey is a read-only reference Playtest consults, so the same measure
judges real and generated maps.

#### 3. Land layout

| Concept | Owns | Never knows |
|---|---|---|
| Frame | The map size and its levels | What fills them |
| Zone | One region's extent, its irregular border and its terrain | The objects in it |
| Water body | Where a sea or a lake lies and its coast | Shipyards, which Settlement places |
| Connection plan | Which zones connect, across land, water, levels and teleports | The tiles of each connection |
| Passage | The stretch of shared border that realises one land connection | The guard that will stand in it |
| Home | Which zone each player starts in, and the ground held for the start town | The town's type or its guard |

Six concepts.

#### 4. Scenery

| Concept | Owns | Never knows |
|---|---|---|
| Walkway | The open ground that links passages, homes and coasts inside a zone | What will stand beside it |
| Border wall | The impassable dressing along zone borders outside passages | Why a passage is where it is |
| Stand | One cluster of decorations shaped after a texture sample | Other stands' contents |
| Clearing | Open ground inside dense vegetation | What will stand in it |
| Decor pick | Which decoration fits a slot on a terrain | The stand's shape |

Five concepts. Clearing is a close call. The problem names clearings as part of the
texture, so it stays.

#### 5. Settlement

| Concept | Owns | Never knows |
|---|---|---|
| Quota | How many objects of each kind a zone receives | Where they go |
| Site | One candidate position: body tiles, visitable tile and approach | Which kind will take it |
| Siting | Choosing the site whose measures best fit the kind's norm | How the norm was learned |
| Guard | The barrier in front of a passage or a valued site: a monster with strength from worth, or a border gate | How the site was chosen |
| Link object | The gate pair, monolith pair or shipyard that realises a level, teleport or water connection | Zone texture |

Five concepts.

#### 6. Playtest

| Concept | Owns | Never knows |
|---|---|---|
| Reach | Whether a hero from each start town reaches every visitable tile, through guards | How the walkway was drawn |
| Conformance | The verdict of Survey against Norm, with its tolerance | How the objects were sited |
| Replay | Whether two runs with the same inputs give the same bytes | What any part does |

Three concepts.

#### 7. Publishing

| Concept | Owns | Never knows |
|---|---|---|
| Scenario | Player slots, teams and the victory condition | Terrain and objects |
| Map file | Encoding a map draft into bytes VCMI reads, in a stable order | How the draft was made |
| Sprite archive | Reading images from the local game install | Maps |
| Render | Drawing a map draft with the game's sprites | The file format |
| Overlay | Drawing one part's analysis over the render, for the developer | The file format |

Five concepts.

## 3. Invariants

1. **A hero reaches every visitable tile from every start town, through guards where they
   stand.** Owner: Reach. Upheld during construction by Passage, Walkway and Siting.
2. **The same seed, size and level flag give the same bytes.** Owner: Replay. Upheld by the
   seed stream, by every part drawing only from its named child stream and iterating in a
   fixed order, and by Map file writing in a stable order.
3. **The game's table decides identity, footprint, visitable tiles and allowed terrain.**
   Owner: Object kind. It fails on any identity it does not hold. Upheld by Norm, which is
   keyed by object kind and carries no shape of its own.
4. **Every object stands on terrain the game allows for it.** Owner: the map draft, which
   refuses an object on a disallowed tile when the object is added. Upheld by Siting and
   Decor pick.
5. **No object covers another object's visitable tile.** Owner: the map draft, on add.
   Upheld by Siting and Stand.
6. **Each player has exactly one start town, in their home zone.** Owner: Scenario. It
   fails when a player slot has no start town. Upheld by Home and Quota.
7. **Every passage has a guard or a border gate, and a monster's strength tracks the worth
   behind it.** Owner: Guard. Upheld by Connection plan, which lists every passage.
8. **The written file reads back into the same map draft.** Owner: Map file.

## 4. Forces and patterns

### Forces

- F1. Two authorities must stay apart. The game's table decides what an object is. The
  corpus decides only how many and where.
- F2. One measure must judge both real and generated maps, or the done-when compares
  unlike things.
- F3. Reading 159 maps is slow and the corpus rarely changes, while a run must finish well
  under 20 seconds at size 72.
- F4. A developer changes one part and wants to see its result alone.
- F5. The same inputs must give the same bytes. A change to one part's draws must not
  reshuffle another part's output, or F4 becomes noise.
- F6. The set of object kinds grows over time. Each new kind brings a quota and a norm, and
  rarely a new rule.
- F7. The vegetation texture varies by terrain.
- F8. The four placement measures are defined against finished scenery. Openness and the
  back touching impassable ground only exist once the decorations stand. Bodies overlap
  vegetation at corpus rates, and visitable tiles almost never do.
- F9. A site must pass several independent rules: allowed terrain, a free visitable tile,
  and an approach from the walkway.
- F10. A site's fit combines four independent measures against their norms.
- F11. The sprite archive is absent on some machines and in tests.
- F12. A generated map is compared against a reference spread with a tolerance.
- F13. The stages before Settlement take 74 seconds at size 72, and Settlement alone takes
  28. A developer who changes Settlement waits for all of them.

### Between parts

- **Sequence of stages handing one map draft along**, from F4. Each part is a stage that
  takes the draft and returns it with its layer added. A developer can stop after any stage
  and render the draft.
- **Stored norms**, from F3. Mapmaking conventions is built by a separate command that
  writes the norms as data. Generation reads the data.
- **Stage drafts cached by their inputs**, from F13. Each stage's output draft is stored,
  keyed by the seed, the size, the level flag and the code of that stage and every stage
  before it. A change to Settlement starts from the stored Scenery draft.
- **Named child seed streams**, from F5. Each part draws from a stream derived from the
  seed and the part's name.
- **Settlement after Scenery**, from F8. Settlement reads open and blocked ground and
  measures against it. The reverse order would make Scenery know every object's norm, which
  breaks its never-knows. Home, from Land layout, holds ground for the start towns so that
  Scenery cannot starve them.

### Inside a part

- Game rules: plain value types over one table literal, from F1. No pattern beyond that.
- Survey and Norm: one plain function per measure over a map draft, from F2.
- Texture sample: data keyed by terrain, from F7. Stand reads it. No strategy per terrain.
- Quota and Siting: table-driven, from F6. One Siting algorithm reads the kind's norm. A
  new kind adds rows, not code.
- Siting's acceptance: a chain of predicates, from F9.
- Siting's fit: a weighted sum of four term functions, from F10.
- Link object: two plain functions, one for gate pairs and one for shipyards. They vary by
  kind but nothing swaps them at run time.
- Sprite archive: a port with a local-install adapter, from F11. Tests pass a fake or skip.
- Conformance: an oracle, from F12. Survey measures, Norm is the reference, the tolerance
  and the verdict are separate.
- Walkway, Border wall, Clearing, Decor pick, Guard, Reach, Replay, Scenario, Map file:
  plain functions. No force varies them today.

### Claims

1. Gameplay after vegetation: re-derived from F8.
2. Sprite top against trees: rejected as a rule. It is one of the four measures, and
   Siting matches it to the corpus spread through F10. A fixed rule would overshoot the 45%
   to 92% overlap rates.
3. Corpus-rate zone totals: re-derived from F1 and F6. Quota reads the rate from Norm.
4. Pipeline of steps: re-derived from F4. A workspace shared by several placement steps is
   rejected. Settlement is one part and hands one draft along.
5. Terrain gate on add: re-derived as invariant 4, owned by the map draft.
6. One ontology from the editor table: re-derived from F1.
7. Gate count and spacing from the corpus: re-derived from F1. Count and spacing are "how
   many and where".
8. Vegetation keeps room for player towns: re-derived from invariant 6 and F8. Home holds
   the ground, and Scenery honours it without knowing why.
9. Vegetation starts from entrances, a walkable web and a sea plan: re-derived. Passage,
   Walkway and Water body carry these, from Land layout to Scenery.

### Open lookups

Section 5 resolves each one.

1. Does one survey measure both corpus and generated maps? Decides whether Survey exists or
   is new, and whether F2 holds today.
2. Are the norms stored as data and read at run time? Decides the stored-norms pattern's
   verdict.
3. Does each stage draw from its own seed stream, or share one? Decides the child-stream
   pattern.
4. Is siting table-driven, or is there one step per object kind? Decides Settlement's
   verdict.
5. Where is reachability checked, and does it pass through guards? Decides Reach.
6. Does adding an object check both allowed terrain and visitable-tile cover? Decides
   invariants 4 and 5.
7. How long does a size-72 run take, stage by stage? This needs a run. Decides whether
   Siting needs precomputed distance fields to stay under 20 seconds.
8. Is there a replay check anywhere? Decides Replay.

## 5. Mapping onto the existing system

### Revision log

- Section 2, Land layout, Connection plan: it now plans teleport connections. The code
  links cut-off zones with monolith pairs after the fact (`steps/portal/geometry.py:46`).
- Section 2, Settlement, Link object: it now covers monolith pairs, for the same finding.
- Section 2, Settlement, Guard: a guard is now a monster or a border gate. The code seals
  small one-passage zones behind a Border Gate (`cli.py:196`).
- Section 3, invariant 7: a passage may hold a border gate instead of a monster, for the
  same finding.
- Section 2, Publishing: Overlay is a new concept. The code draws zone, passage, pocket,
  guard and blocking overlays for the developer (`renderers/overlays/`).
- Section 4: F13 and the stage-draft cache are new. A size-72 run took 102 seconds, 74 of
  them before Settlement starts.

### Parts

| Part | Verdict | Finding |
|---|---|---|
| Game rules | Exists | `ontology.py` holds identity, footprint and allowed terrain from the editor table. Tile join and Worth need a reshape. |
| Mapmaking conventions | Reshape | Two surveys measure at different tiles, the placement norms are not stored, and a run reads the corpus three times. |
| Land layout | Reshape | Scenery builds the land plan, and connectivity is repaired after Settlement instead of planned. |
| Scenery | Reshape | The border wall is split: half before Settlement, half after it. |
| Settlement | Reshape | Six steps site objects with their own code over a shared mutable workspace, and Siting maximizes one measure instead of fitting four. |
| Playtest | New | No run checks reach or replay, and the conformance report gives means with no verdict. |
| Publishing | Exists | The writer, the render and the overlays match. Scenario hides inside the writer. |

### Concepts

#### 1. Game rules

| Concept | Verdict | Where, and the finding |
|---|---|---|
| Object kind | Exists | `ontology.py:3563` `identity_of`. It matches. |
| Footprint | Exists | `ontology.py:3525` `mask_of`. It matches. |
| Terrain allowance | Exists | `ontology.py:3581` `allowed_on`, read by `validate.py:39`. It matches. |
| Terrain kind | Not mapped | None of the files I read owns it. |
| Tile join | Reshape | `kit/tiling.py:64` learns the join table from all 159 maps on every run. The design is right: the table is a game fact, so it belongs in stored data that Game rules reads. |
| Worth | Reshape | Guard strength comes from a per-resource level table (`steps/gameplay/mines.py:170`) plus a 25% chance of one level more (`steps/gameplay/site.py:459`). No scale compares a mine, a bank and a chest. The code is wrong, because the problem asks strength to track value. |

#### 2. Mapmaking conventions

| Concept | Verdict | Where, and the finding |
|---|---|---|
| Corpus | Reshape | `extract_vmap.py` and `kit/objects.py:58` read the maps. A generate run calls that reader 477 times, from `kit/tiling.py:64`, `steps/terrain_gen/markov.py:30`, `markov.py:104` and `steps/terrain_gen/macro_topo.py:451`. That is 69 of 101 profiled seconds. The code is wrong: a run must read stored norms only. |
| Survey | Reshape | `corpus_match.py:43` measures depth, gate, open and back at the visitable tile. `steps/gameplay/mines.py:377` counts objects at their anchor. The code is wrong on F2: one survey must serve both sides. |
| Norm | Reshape | `data/pp/*.json` stores vegetation, gameplay, gate and terrain stats. The gameplay norm is built inside the gameplay package (`mines.py:452`) and keyed by purpose and terrain, not by object kind. The four placement measures have no stored norm, and `guard_frac` (`mines.py:235`) is stored but no caller reads it. |
| Texture sample | Exists | `steps/vegetation/stats.py:310` stores one file per terrain. It matches. |

#### 3. Land layout

| Concept | Verdict | Where, and the finding |
|---|---|---|
| Frame | Exists | `cli.py:182`, the size and the level flag. |
| Zone | Exists | Zones come from a same-terrain flood fill after the terrain is drawn. The order differs from the design, but the owns and never-knows match. |
| Water body | Exists | `steps/zone_plan.py:152` finds the bodies. |
| Connection plan | Reshape | No plan says which zones connect. `steps/zone_plan.py:318` plans entrances per zone, and `steps/portal/geometry.py:46` links unreachable zones with portals after Settlement. The code is wrong: a repair after the fact hides a layout that failed. |
| Passage | Exists | `steps/zone_plan.py` builds the entrance bands. The border step closes the rest. |
| Home | Reshape | `steps/zone_plan.py:278` holds room for each town. When a home zone has no room, `steps/gameplay/step.py:269` moves the town to the largest zone and prints a warning. The code is wrong: that breaks invariant 6 in silence. |

Claim 9 shows a second mismatch. `steps/vegetation/step.py:99` builds the land plan inside
Scenery, so the code's Scenery owns entrances and the sea plan. The design keeps them in
Land layout, and the code should follow.

#### 4. Scenery

| Concept | Verdict | Where, and the finding |
|---|---|---|
| Walkway | Exists | The walkable web from `steps/zone_plan.py`, passed to the sampler as `prot` (`steps/vegetation/step.py:138`). |
| Border wall | Reshape | `steps/vegetation/step.py:171` seals borders before Settlement. `cli.py:198` runs a second border step after Settlement. The code is wrong on F8: a wall added after siting changes openness and back after Siting measured them. |
| Stand | Exists | `steps/vegetation/sample.py:293`, a sampler fitted per terrain. |
| Clearing | Exists | It lives inside the sampler's energy (`sample.py:429`), not as its own concept. The design keeps it separate on paper only. No change is needed. |
| Decor pick | Exists | `ontology.py:3606` `decor_pool`. |

#### 5. Settlement

| Concept | Verdict | Where, and the finding |
|---|---|---|
| Quota | Exists | `steps/gameplay/draw.py:72` draws the zone total from corpus density. It matches. |
| Site | Exists | `steps/gameplay/site.py`, the zone spot search. |
| Siting | Reshape | `site.py:380` takes the candidates near the best intensity and keeps the one with the highest back score. That maximizes one measure, where the design fits four to the spread. Five more steps site their own objects through `steps/placement.py:218`. The code is wrong on F6 and on the done-when. |
| Guard | Reshape | `site.py:459` guards every mine. The corpus guards 64%. Section 7 decides. |
| Link object | Exists | Gate pairs and shipyards in the gameplay package, monolith pairs in the portal step. |

The six placement steps share one mutable `PlacementWorkspace` (`pipeline.py:102`), whose
zone record carries many fields that each step writes (`pipeline.py:59`). The design has
one Settlement part and no shared mutable state. The code is wrong, because a change to one
step's writes shifts what every later step reads.

#### 6. Playtest

| Concept | Verdict | Where, and the finding |
|---|---|---|
| Reach | New | `kit/reachability.py:186` checks towns and mines from one start town. Its only caller is a test. The widened check lives in `kit/reachability.py`, and the generate command runs it after the last stage. `steps/vegetation/step.py:33` upholds reach by failing on a walled-off pocket. |
| Conformance | Reshape | `corpus_match.py:180` reports means only, with no spread, tolerance or verdict. It copies the step list from `cli.py`, and `make check` does not run it. |
| Replay | New | Module tests check determinism in parts (`steps/gameplay/mines_test.py:23`, `steps/vegetation/sample_test.py:31`). No test compares two whole maps byte for byte. `steps/seed_sweep_test.py:18` checks only that steps add objects. |

#### 7. Publishing

| Concept | Verdict | Where, and the finding |
|---|---|---|
| Scenario | Reshape | `renderers/vmap.py:167` sets slots, teams and the victory inside the file writer. It fails only on a team count mismatch (`vmap.py:159`). It cannot own invariant 6 from there. |
| Map file | Exists | `renderers/vmap.py:28`, with a round-trip test at `renderers/vmap_test.py:64`. |
| Sprite archive | Exists | `renderers/sprites.py:223` returns nothing when the archive is absent, and the render tests skip. |
| Render | Exists | `renderers/png.py`. |
| Overlay | Exists | `renderers/overlays/`. |

### Invariants against the code

1. Reach has no owner at run time.
2. Replay has no owner.
3. Object kind: `ontology.py` owns it.
4. The map draft owns it: `models/map_state.py:263` refuses a disallowed terrain on add.
5. The map draft owns it: `models/map_state.py:103` refuses a covered visitable tile. It
   lets a guard stand on an entrance, which fits "through guards where they stand".
6. Nothing owns it. `steps/gameplay/step.py:269` moves a start town out of its home zone.
7. Guards stand on passages. Their strength does not track worth, per Worth above.
8. Map file owns it through the round-trip test.

### What the code has that the design lacked

- Border-gated pockets and their treasure (`cli.py:196`, `cli.py:197`): a missed concept.
  Guard now covers border gates.
- Monolith pairs for cut-off zones (`cli.py:199`): a missed concept as a connection kind.
  The repair after Settlement is waste once Connection plan plans teleports.
- Developer overlays (`renderers/overlays/`): a missed concept, now Overlay.
- Seer-hut quests (`cli.py:200`): waste for this problem, which puts quests out of scope.
- Guarded pocket caches and free resource piles (`cli.py:200`, `cli.py:201`): not missed.
  Quota, Siting and Guard cover pickups.
- The typed value registry (`pipeline.py`): it fits the design as the way the land plan
  crosses stages, as long as the values it carries are not mutated.
- The object catalog render (`cli.py` `render-ontology`): outside this problem. It serves
  whoever maintains the object table and needs no concept here.

### Claims against the code

| Claim | The code | The design |
|---|---|---|
| 1. Gameplay after vegetation | Follows, `cli.py:187` then `cli.py:188`. The late border step breaks it. | Follows, from F8. |
| 2. Sprite top against trees | Follows, `site.py:380` maximizes back. | Rejects it. Siting fits the spread. |
| 3. Corpus-rate zone totals | Follows, `draw.py:67`. | Follows. |
| 4. Step pipeline with a shared workspace | Follows, `pipeline.py:102`. | Keeps the stages, rejects the shared workspace. |
| 5. Terrain gate on add | Follows, `models/map_state.py:263`. | Follows, invariant 4. |
| 6. One ontology from the editor table | Follows for objects. Tile joins come from the corpus. | Follows. |
| 7. Gate count and spacing from the corpus | Follows, `data/pp/gate_stats.json`. | Follows. |
| 8. Vegetation keeps room for towns | Follows, `steps/zone_plan.py:278`, with a silent fallback. | Follows, through Home. |
| 9. Vegetation starts from the land plan | Follows, but Scenery builds the plan itself. | Follows, with Land layout building it. |

### Lookups

1. One survey for both sides? No. The two measure at different tiles. F2 fails today.
2. Stored norms? In part. The terrain step still reads all 159 maps three times per run.
3. A seed stream per stage? Each concept salts its own generator from the one seed. Two
   pairs collide: `steps/gated/placer.py:327` and `steps/treasure/fill.py:284` use the same
   formula, and `steps/loot/caches.py:655` and `steps/scatter/scatter.py:79` share a salt.
   Named child streams stay in the design, because a name cannot collide by accident.
4. Table-driven siting? No. One hand-ordered step plus five more placement steps.
5. Where is reach checked? Only in a test, and only for towns and mines.
6. Does add check terrain and cover? Yes, both.
7. Size-72 timing, seed 3: 102 seconds in all. The stages up to Scenery take 74 seconds.
   Settlement and publishing take 28. In the profile, corpus reads take 69 of 101 seconds
   and the vegetation sampler takes 19. This added F13.
8. A replay check? No whole-map check exists.

## 6. Slices

1. **Conformance verdict for mines.** One survey measures corpus and generated maps at the
   visitable tile. Norm stores the four measures' spread per object kind. Generate prints
   pass or fail per measure. Touches Survey, Norm and Conformance. Done when a size-72 run
   prints a verdict for mines and `make check` runs it on one seed.
2. **Fast loop.** Store the tile-join table and the terrain model as data, and cache each
   stage's draft by its inputs. Touches Corpus, Norm, Tile join and the stage cache. Done
   when a run reads no corpus map, and a rerun after a Settlement change skips every stage
   before it.
3. **Reach and Replay at run time.** Touches Reach, Replay and the seed stream. Done when
   generate fails on an unreachable visitable tile from any start town, and a test
   generates one seed twice and compares the bytes.
4. **Mines fit the spread.** Siting fits the four measures to the norm for mines, and Guard
   draws the guard rate from Norm. Touches Siting, Guard and Worth. Done when mines pass
   Conformance on the twelve sweep seeds.
5. **One Settlement.** The border wall moves into Scenery. The placement steps merge into
   one Settlement stage with no shared mutable workspace, and each other kind arrives as
   table rows. Touches Border wall, Quota, Siting, Guard and Link object. Done when every
   kind passes Conformance on the sweep seeds.
6. **Home owns the start town.** Scenario leaves the file writer and fails when a player has
   no start town in their home zone. Touches Home and Scenario. Done when a seed with no
   room fails with a message instead of moving the town.

## 7. Open decisions

1. **Mine guard rate.** The code guards every mine, citing a user report of unguarded
   mines (`steps/gameplay/mines.py:170`). The problem gives the corpus rate as 64%. Options:
   keep 100%, or draw the rate from Norm. Recommendation: draw it from Norm. Reason: the
   problem lists the rate as one of the conventions that make a map read as hand-made.
2. **Where the terrain norms live.** Options: keep learning the tile joins and the terrain
   model from the corpus on each run, or store them as data. Recommendation: store them.
   Reason: the corpus reads take two thirds of a run.
3. **Settlement's own time.** Settlement and publishing take 28 seconds, over the 20-second
   target even with a cached Scenery draft. Options: profile and speed up Settlement, or
   read the target as "the changed part alone". Recommendation: profile it after slice 2.
   Reason: I have not measured where the 28 seconds go.
4. **The border wall after Settlement.** Options: keep the late border step, or move the
   whole wall into Scenery. Recommendation: move it. Reason: a wall added after siting
   changes the measures Siting fitted.
5. **The shared placement workspace.** Options: keep it, or hand an immutable land plan and
   Scenery's open ground forward as values. Recommendation: hand values forward. Reason:
   each step's writes change what every later step reads.
6. **Portal repair.** Options: keep repairing cut-off zones after Settlement, or plan
   teleports in Connection plan and let Reach fail on a cut-off zone. Recommendation: plan
   them. Reason: the repair hides a layout that failed.
7. **Seer-hut quests.** Options: remove them, or keep them behind a flag that is off for
   conformance runs. Recommendation: keep them behind a flag. Reason: the code works, and
   the problem only puts quests outside this design.
8. **Parked: repository structure.** Settlement spans six step packages, the gameplay norm
   lives inside the gameplay package, and `docs/architecture.md` describes an engine that
   no longer exists. This reaches beyond this problem. Load `target-architecture` for it.
