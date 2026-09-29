# Random maps that read as hand-made: a top-down design

## What I saw before writing this note

I saw parts of the existing solution before section 5. The design below has to be read
with that in mind.

- Before the skill loaded, my context already held the root `AGENTS.md`, which lists the
  package layout, the step names and the object ontology. It also held the memory index line
  "all gameplay placed after vegetation" and the recent commit subjects.
- After the skill loaded, I read `README.md` and the `vcmi-mapgen-maps` skill. The version
  of the skill I loaded first allowed both. The version on disk, which I re-read before
  writing, forbids both before section 5. Their design decisions are recorded as claims in
  section 1b.
- A directory listing showed me the file names under `docs/design/`. I opened none of them.

Each part and concept below passed the test "would I have named this without having seen
the solution?" Two needed a note. The open way in Scenery echoes the README's "walkable
web". I would have named it anyway, because a reachability guarantee over a map full of
impassable decoration needs a reserved path. The standing rule echoes a terrain gate named
in `AGENTS.md`. The problem's own guarantees name that rule, so it stays.

## 1. Problem

A VCMI player who wants a fresh map for each session can wait days for a mapmaker, or take
a generated map that gives itself away at a glance: objects alone in bare clearings, forests
like uniform noise, zones like blobs. The player wants a new map every time that looks and
plays like a hand-made one.

Done, as the player and the developer see it:

- The VCMI editor opens every generated map without errors, and a two-player game starts
  on it.
- A reviewer who compares a generated render with corpus renders cannot pick out the
  generated one by bare clearings, uniform forests or blob zones.
- For each object type, four placement measures fall within the corpus spread: depth from
  the zone edge, walking distance to the nearest passage, openness around the visitable
  tile, and how much of the sprite's back touches impassable ground.
- Rates match the corpus: about 3 gameplay objects per 100 zone tiles at every size, 64% of
  mines guarded, towns overlapping vegetation about 92% of the time, visited tiles covered
  under 0.4% of the time.
- A developer changes one part of the generation and sees the result in under 20 seconds
  at size 72.

Out of scope:

- Victory conditions other than "defeat all".
- Timed events, scripts and quests.
- Editing or extending an existing map.
- Improving the corpus itself, or adding maps from other game versions.

## 1b. Claims

The problem statement is a problem, not a solution. The README and the maps skill I read
state design decisions, so each is recorded here as a claim for section 4 to re-derive or
reject.

1. Zones grow by capacity-constrained growth with textured borders. (README)
2. Shores and terrain edges use corpus-learned transition tiles. (README)
3. Vegetation comes from a corpus-fitted Gibbs marked point process with the clustering
   statistics of real maps. (README)
4. A protected walkable web keeps every zone entrance reachable. (README)
5. Every gameplay object is placed after vegetation, with its back against it. (README,
   memory)
6. Loot is unguarded scatter along routes plus guarded caches in pockets with a monster on
   the mouth. Guard level scales with guarded value. (README)
7. Subterranean gate pairs connect the two levels as part of the macro layout. (README)
8. Every town gets its sawmill and ore pit. (README)
9. One ontology is the single source of object identity, footprint, terrain coupling and
   decoration category. The corpus informs only spatial statistics. (`AGENTS.md`)
10. Reading the corpus re-derives each footprint from the game's table instead of trusting
    the file's mask. (maps skill)
11. Zones in a map are found by a 4-connected flood fill by terrain, with water and rock as
    barriers. (maps skill)
12. The generator is a pipeline of steps sharing one placement workspace, with a way to stop
    after a step. (`AGENTS.md`)
13. The terrain placement rule is checked when an object is added to the map. (`AGENTS.md`)
14. Corpus-derived priors are stored as data files. (`AGENTS.md`)
15. Most placed objects use the editor's random classes. (README, also the problem)

## 2. Parts and concepts

### Level 1: parts

| Part | Owns | Never knows | Hands to |
|---|---|---|---|
| Conventions | What hand-made maps look like, in numbers, and how to measure any map | How a map gets generated | Rates and textures to Geography, Scenery and Population. Measures and corpus spreads to Inspection |
| Object rules | What the game says each object is: identity, footprint, visitable tiles, allowed terrain, worth | Any corpus statistic, any particular map | Answers to every other part |
| Geography | The land: zones, their terrain, seas and lakes, levels, and the passages between zones | Which objects will stand where | The shaped land to Scenery and Population |
| Scenery | Impassable decoration and its texture: forests, mountain stands, rocks, clearings | What any gameplay object is worth | The decorated land to Population |
| Population | Everything a hero interacts with: towns, mines, dwellings, visitables, crossings, guards and pickups | How the texture was sampled | The finished map to Inspection |
| Inspection | Judging a finished map against the hard guarantees and the corpus spread | How the map was made | A verdict to Delivery and to the developer |
| Delivery | The files people open: the editor map with its player slots, and the picture | How the map was made | Files on disk |

Flow: Conventions studies the 159 real maps once and keeps the numbers. Geography shapes
the land from the request. Scenery dresses it. Population settles gameplay into the dressed
land. Inspection judges the result. Delivery writes the editor map and the picture. Object
rules answers every part that asks what an object is or where it may stand.

In plain words: learn how real mapmakers work, know the game's rules for each object,
shape the land, plant the forests and mountains, settle the towns, treasure and monsters,
check the result, and hand over the files.

Shared value types, owned by no part:

- **Request**: seed, size, level flag, players and teams.
- **Seed stream**: the source of every random draw, derived from the request's seed.
- **Map**: the tile grid, each tile's terrain, and the placed objects. Every part reads it,
  and the generating parts add to it. Conventions also reads real maps into it, so one
  measure works on both kinds.

### Level 2: concepts

**Conventions**

| Concept | Owns | Never knows |
|---|---|---|
| Real map | Reading one `.h3m` into a Map | Any statistic |
| Zone reading | Cutting any Map into zones and the passages between them | Whether the map is real or generated |
| Placement measure | The four measures of one placed object: depth, walking distance to a passage, openness, back contact | Generation |
| Rate | Per-zone counts: objects per 100 tiles, mix by type, guard share, random-class share | Where objects go |
| Texture | Per-terrain clustering of forests, mountain stands and clearings | Which sampler consumes it |
| Convention book | The stored numbers, and whether they are stale against the corpus | How each number was measured |

**Object rules**

| Concept | Owns | Never knows |
|---|---|---|
| Object kind | Identity from the game's table, including the random classes | Footprint geometry |
| Footprint | Blocked, visitable and empty tiles, anchored at the bottom-right | Terrain |
| Terrain allowance | The terrains an object may stand on | Footprint |
| Approach | The directions from which a hero may enter the visitable tile | Map contents |
| Role | Whether an object is a town, mine, dwelling, bank, shrine, crossing, guard, pickup or decoration | Corpus rates |
| Worth | The value a hero gains from an object, for guard strength | Guards |
| Standing rule | Whether one object may stand at one spot of a Map: in bounds, allowed terrain, no visitable tile covered | Why the caller wants it there |

**Geography**

| Concept | Owns | Never knows |
|---|---|---|
| Zone plan | Which zones exist: count, target size, terrain, owner player | Zone shape |
| Zone shape | Which tiles belong to which zone, with irregular borders | Objects |
| Water body | Where seas and lakes lie | Shipyards |
| Passage | A wide stretch of shared border that joins two zones | Guards |
| Level link | Which zones on the two levels connect | Gate objects |
| Terrain painting | Each tile's terrain image, including shore and edge transitions | Zones |

**Scenery**

| Concept | Owns | Never knows |
|---|---|---|
| Open way | The reserved ground that keeps every passage and every future site reachable | Stand texture |
| Stand | A cluster of trees, mountains or rocks with its terrain's texture | Gameplay objects |
| Clearing | Open ground left inside and between stands | Which object will use it |
| Border seam | Impassable decoration along every zone border outside its passages | Guards |
| Decoration choice | Which decoration sprite fills a spot, from those the terrain allows | Stand shape |

**Population**

| Concept | Owns | Never knows |
|---|---|---|
| Zone budget | How many objects of which type a zone receives | Where they go |
| Site | A candidate spot for one object, scored against its type's corpus measures | Budget |
| Start town | One town per player in its own zone, with its nearby mines | Other players' zones |
| Crossing | Objects that change travel space: gate pairs between levels, shipyards onto water | Guard strength |
| Guard | The monster on a passage, a mine or a treasure, and its strength from the worth behind it | Pickup layout |
| Pickup | Resources, artifacts and chests, loose or guarded | Guard strength |

**Inspection**

| Concept | Owns | Never knows |
|---|---|---|
| Reachability verdict | Whether every visitable object is reachable from every start town, through guards | Scenery |
| Standing audit | Whether every placed object passes the standing rule on the finished map | Placement order |
| Spread verdict | Whether each type's measures fall within the corpus spread, with a tolerance | How the measures are computed |

**Delivery**

| Concept | Owns | Never knows |
|---|---|---|
| Map file | The `.vmap` bytes: header, terrain, objects | Rendering |
| Roster | Player slots, teams and the "defeat all" victory, tied to start towns | Terrain |
| Picture | The PNG drawn with the real sprites | The file format |
| Sprite source | Reading sprite frames from the local game archives | The picture layout |

Two concepts need a word on ownership. Zone reading sits in Conventions and Inspection
uses it through Placement measure, so it is not shared. Map, Request and Seed stream are
shared value types, not a sign the split is wrong: they carry data and enforce one rule
each.

## 3. Invariants

| Invariant | Part | Concept |
|---|---|---|
| A hero reaches every visitable object from every start town, through guards where they stand. | Inspection | Reachability verdict. It sees the finished whole and rejects a map that fails. |
| Every random draw comes from the request's seed. | Shared | Seed stream |
| Written bytes depend only on the Map: no clock, no unordered iteration. | Delivery | Map file |
| Identity, footprint, visitable tiles and allowed terrain come only from the game's table. | Object rules | Object kind, footprint and allowance each answer one question. Object kind is the only entry that takes a raw game id. |
| Every object stands on terrain the game allows for it. | Object rules | Standing rule, checked on every add to the Map |
| No object covers another object's visitable tile. | Object rules | Standing rule |
| Every visitable object has at least one approach direction. | Object rules | Approach |
| The corpus decides only counts and positions. | Conventions | Convention book. It stores rates, textures and spreads, never identities or footprints. |
| One start town per player, each in its own zone. | Population | Start town |
| Guard strength rises with the worth behind the guard. | Population | Guard |
| Every passage between zones carries a guard. | Population | Guard |
| A passage is a stretch of border, never a one-tile corridor. | Geography | Passage |
| A hero crosses from one zone to another only at a passage. | Scenery | Border seam |
| Each zone's gameplay count stays within the corpus spread of the rate. | Population | Zone budget |
| Gate ends come in pairs, and a shipyard touches navigable water. | Population | Crossing |

## 4. Forces and patterns

### Forces

1. **The corpus rarely changes, and measuring 159 maps is slow.** Generation must stay
   under 20 seconds at size 72.
2. **A developer changes one part and inspects it.** The generation must stop after any
   part and render what exists.
3. **Changing one part must not reshuffle the others.** Otherwise a change to Scenery moves
   every town and the comparison means nothing.
4. **The sprite archives exist only on machines with a VCMI install.** Tests must run
   without them.
5. **A candidate site is judged on four independent measures.** Each has its own corpus
   spread per object type.
6. **Texture varies by terrain type, independently of zone shape.**
7. **The finished map is compared against a reference with a tolerance.** The same
   measure applies to real and generated maps.
8. **Object types are many and fixed by the game's table.** New ones arrive through the
   table, not through code.
9. **Optional water and an optional underground level vary per request.**
10. **Byte-identical output.** The same request gives the same file.

### Between parts

- **A sequence of stages handing one Map along** (forces 2 and 10). Geography, Scenery and
  Population each take the Map and return it enriched. A stop point after any part feeds
  Delivery's picture directly.
- **The Convention book as a cache stored as data, keyed by the corpus** (force 1). Every
  run reads it. Only a corpus change rebuilds it.
- **One seed stream split into a named substream per part** (force 3). Scenery's draws
  never shift Population's.

### Inside a part

| Concept | Pattern | Force |
|---|---|---|
| Convention book | Data file with a staleness key | 1 |
| Placement measure, Spread verdict | Oracle: measure, reference, tolerance and verdict as separate pieces | 7 |
| Site | Weighted sum of four term functions, one per measure, with per-type targets from the book | 5 |
| Stand | One sampler parameterised by the terrain's texture record | 6 |
| Border seam | Plain function over the zone labels and the passages | No force |
| Sprite source | Plain reader of the local archives. Tests that need it skip when it is absent. No second implementation exists, so a port has no force | 4 |
| Object kind, Footprint, Terrain allowance, Role, Worth | Plain lookups over a data table | 8. No registry, because the table already is one. |
| Standing rule | One function with early returns | No force for a chain. The rules are few and fixed by the game. |
| Water body, Level link | Plain functions that return nothing when the request asks for none | 9 |
| Everything else | Plain functions and plain value types | No force |

### Claims

| Claim | Verdict |
|---|---|
| 1. Capacity-constrained zone growth | Re-derived for Zone shape. The zone plan fixes target sizes, and growth that honours them is the plain answer. The textured border is kept because the problem names blob zones as a tell. |
| 2. Corpus-learned transitions | Re-derived for Terrain painting. Borders must look hand-drawn. |
| 3. Gibbs marked point process | Re-derived as the Stand sampler. Force 6 needs clustering statistics per terrain. The specific model is an implementation choice to confirm in section 5. |
| 4. Protected walkable web | Re-derived as Open way, from the reachability invariant. |
| 5. Gameplay after vegetation | Open. The back-contact measure and the overlap rates favour settling objects into existing scenery. Towns need space the scenery must leave. Decision 1 in section 7. |
| 6. Loot scatter and guarded pockets | Split. Guarded treasure re-derives from the guard invariant. The "along routes" layout has no force in the problem. Section 5 checks it against the Site measures. |
| 7. Gates as part of the macro layout | Rejected as stated. Which zones link belongs to Geography. The gate objects belong to Population, as a Crossing. |
| 8. Sawmill and ore pit per town | Kept inside Start town. Hand-made maps give each start its basic mines. Section 5 checks whether the corpus measures it. |
| 9. One source of object identity | Re-derived. It is the identity invariant. |
| 10. Masks from the table when reading the corpus | Re-derived. It follows from the identity invariant. |
| 11. Flood-fill zone reading | Re-derived for Zone reading on real maps. A real map carries no zone labels, and terrain plus barriers is the domain's own boundary. |
| 12. Pipeline of steps sharing one workspace | Half kept. The sequence re-derives from force 2. A shared workspace beside the Map has no force. Everything a later part needs lives on the Map or in its own return value. |
| 13. Terrain rule checked on every add | Re-derived as Standing rule. |
| 14. Priors stored as data | Re-derived from force 1. |
| 15. Random classes | Re-derived inside Zone budget. It is a corpus rate, and the problem names it. |

### Open lookups

1. Is there a measure of the four placement measures on real and generated maps today?
   Placement measure and Spread verdict wait on it.
2. How long does a size-72 run take, per part? The stop-point design waits on it.
3. Does adding an object to the Map check terrain and visitable-tile coverage both? The
   Standing rule verdict waits on it.
4. Does anything check reachability on the finished map, and what happens on failure?
   Reachability verdict waits on it.
5. Does the seed stream split per part? Force 3's pattern waits on it.
6. Where does an object's worth come from? Worth waits on it.
7. How are the corpus numbers stored and rebuilt? Convention book waits on it.
8. Is anything besides the Map shared between the generating parts? Claim 12 waits on it.

## 5. Mapping onto the code

Two findings below changed the design, and each change sits in its own section. Border
seam joined Scenery in section 2, with its invariant in section 3, because the code seals
zone borders and the design had no owner for it. Sprite source lost its port in section 4,
because the code meets force 4 with a skip and no second source exists.

### Parts

| Part | Verdict | Where it lives, and the mismatch |
|---|---|---|
| Conventions | Reshape | Each generating step mines its own numbers: `steps/vegetation/stats.py`, `steps/gameplay/mines.py`, `steps/gate/gates.py`, `steps/terrain_gen/macro_topo.py`. The part knows how the map gets generated, which the design forbids. The code is wrong: four caches drift apart. |
| Object rules | Reshape | `ontology.py` holds identity, footprint and terrain. The standing rule is split between `validate.py` and `models/map_state.py`. Approach sits in `kit/objects.py`. Worth has no home. |
| Geography | Reshape | `steps/terrain_gen/` plans and grows zones, then `steps/segment/` throws the labels away and re-reads zones by flood fill. Passages are planned inside the vegetation step. |
| Scenery | Reshape | `steps/vegetation/` also plans passages and seals borders. Through `steps/zone_plan.py:22-28` it imports mine, shipyard, water and site code, so Scenery knows Population. |
| Population | Reshape | Seven steps (`gameplay`, `gated`, `treasure`, `border`, `portal`, `loot`, `scatter`) pass state through `PlacementWorkspace` (`pipeline.py:59-112`) beside the Map. |
| Inspection | New | No part judges the finished map. One reachability check runs inside the portal step, and the measures live in a report tool with no verdict. |
| Delivery | Reshape | `renderers/vmap.py` and `renderers/png.py` exist. The file is not byte-identical across runs. |

### Concepts

**Conventions**

| Concept | Verdict | Evidence |
|---|---|---|
| Real map | Exists | `h3m.py`, `extract_vmap.py` and `readers/` read a corpus map into a Map. |
| Zone reading | Exists | `kit/segmentation.py` and `kit/terrain_segment.py` serve real and generated maps alike. |
| Placement measure | Reshape | `corpus_match.py` computes the four measures for corpus and generated zones. It builds its own pipeline (`corpus_match.py:27-38`) and prints a report, so the measure is not reusable by Inspection. |
| Rate | Exists | `steps/gameplay/mines.py:452-474` mines the per-zone rates that `steps/gameplay/draw.py` consumes. |
| Texture | Exists | `steps/vegetation/stats.py:390-394` stores one record per terrain in `data/pp/veg_<terrain>.json`. |
| Convention book | Reshape | Four owners with four rules. Vegetation rebuilds only when the file is missing (`stats.py:390-394`). Gates carry a `_version` key (`gates.py:124-148`). Rates and macro stats have their own caches (`mines.py:36-37`, `macro_topo.py:49-50`). No key ties any of them to the corpus. The code is wrong. |

**Object rules**

| Concept | Verdict | Evidence |
|---|---|---|
| Object kind | Exists | `identity_of` and `decode_identity` (`ontology.py:3563`, `3760`). |
| Footprint | Exists | `mask_of` (`ontology.py:3525`). |
| Terrain allowance | Exists | `terrains_of` and `allowed_on` (`ontology.py:3576`, `3581`). |
| Approach | Reshape | `front_tiles` (`kit/objects.py:190`) infers the approach from the mask's last row instead of reading it from the game's table. It lives in the corpus loader, outside Object rules. The code is wrong on both counts. |
| Role | Exists | The `purpose` strings and `cluster_of` (`ontology.py:305`, `3704`). |
| Worth | New | `ontology.py` knows monster levels and artifact tiers (`ontology.py:3680`, `3693`), and no object has a worth. It will live in `ontology.py` beside them. |
| Standing rule | Reshape | `MapState.add_objs` (`models/map_state.py:263-281`) runs whatever rules the caller passes, plus `_clash` (`map_state.py:103-119`). The terrain rule is `TerrainGate` (`validate.py:38-50`). `_clash` carries gameplay exceptions keyed on purpose strings. `CoverIndex` (`map_state.py:134-174`) and each step's pre-checks repeat the rule. A caller can pass a weaker rule through the `PlacementRules` protocol (`map_state.py:181-182`). The code is wrong: the rule has one owner in the design and several in the code. |

**Geography**

| Concept | Verdict | Evidence |
|---|---|---|
| Zone plan | Reshape | `_sample_areas` and `_assign_terrains` (`macro_topo.py:307`, `340`) plan count, size and terrain. The owner player is chosen later, inside the vegetation step (`vegetation/step.py:99-102`). |
| Zone shape | Reshape | `_grow` (`macro_topo.py:383`) grows zones to capacity. `steps/segment/step.py` then re-derives zones by flood fill, so the planned shape is lost. The code is wrong: Zone reading is for maps with no labels, and a generated map has them. |
| Water body | Exists | `_water_mask` (`macro_topo.py:179`). |
| Passage | Reshape | `plan_zones` and `plan_player_zones` run inside `VegetationStep.run` (`vegetation/step.py:99-102`). The code is wrong: a passage is land, and the scenery should receive it. |
| Level link | Reshape | `place_gate_pairs` (`steps/gameplay/gate_pairs.py:102`) picks the linked zones from wherever a gate fits best. No part decides the link first. |
| Terrain painting | Exists | `steps/terrain_gen/step.py` and `markov.py`. `markov.py:173` draws from `random.Random(3)`, outside the request's seed. |

**Scenery**

| Concept | Verdict | Evidence |
|---|---|---|
| Open way | Reshape | The walkable web in `steps/zone_plan.py` imports Population code (`zone_plan.py:22-28`). |
| Stand | Exists | The vegetation sampler with per-terrain records (`steps/vegetation/stats.py`). |
| Clearing | Reshape | Town room is reserved by name (`town_clear`, `town_blk`, `town_room` in `steps/gameplay/step.py`). The clearing knows it is for a town. Decision 1 settles whether that is allowed. |
| Decoration choice | Exists | `decor_pool` (`ontology.py:3606`). |
| Border seam | Reshape | Two owners: `seal_borders` (`vegetation/step.py:171-210`) and `BorderStep` (`steps/border/step.py`, `border_seal.py`). |

**Population**

| Concept | Verdict | Evidence |
|---|---|---|
| Zone budget | Exists | `steps/gameplay/draw.py` draws a per-zone total at the corpus rate, forced objects included. |
| Site | Reshape | `ZoneSite.intensity_order` (`site.py:362-367`) weighs edge depth, gate distance and openness (`mines.py:514-526`). Back contact only breaks ties inside a 3-tile window (`site.py:380-403`). The code is wrong: the problem names back contact as one of the four measures. |
| Start town | Reshape | `_player_towns` (`gameplay/step.py:344-352`) fills from spare towns in any zone. A failure prints a warning (`gameplay/step.py:58-63`, `280-281`). The code is wrong: two players can share a zone. |
| Crossing | Exists | `place_gate_pairs` and `place_shipyards` (`shipyards.py:109`). A seed 3 run warned "no seaport placed on shore near zone(s) [1, 3, 5]" and then added two by a fallback. |
| Guard | Reshape | Five rules set guard strength: `MINE_GUARD_LVL` plus a bump (`site.py:459-463`), zone area (`border/entrances.py:30-33`), a fixed 3 or 4 (`border_seal.py:55`, `66`), pocket depth (`loot/caches.py:720`) and a fixed 3 (`gate_pairs.py:98`). None reads a worth. Every mine is guarded (`site.py:428-429`, `446`, `mines.py:166-167`), against the corpus 64%. |
| Pickup | Exists | `steps/loot/caches.py`, `steps/treasure/fill.py` and `steps/scatter/scatter.py`, split across three steps. |

**Inspection**

| Concept | Verdict | Evidence |
|---|---|---|
| Reachability verdict | Reshape | `unreachable_targets` (`steps/portal/geometry.py:46`) runs inside `PortalStep` (`portal/step.py:119-126`) and raises. It walks from the first open target, not from each start town. Loot and scatter place objects after it runs. `kit/reachability.traverse` (`kit/reachability.py:215-244`) is the second walker, runs only in a test, and cites scripts that do not exist. |
| Standing audit | New | Nothing re-checks the finished map. It will live beside the reachability verdict. |
| Spread verdict | New | `corpus_match.py` reports numbers with no tolerance. |

**Delivery**

| Concept | Verdict | Evidence |
|---|---|---|
| Map file | Reshape | `writestr(name, data)` (`kit/vmap/writer.py:112-114`) stamps each entry with the wall clock. Two runs of seed 3 gave identical contents and different bytes from byte 11. The code is wrong. |
| Roster | Exists | `_apply_playability` (`renderers/vmap.py:167`). |
| Picture | Exists | `renderers/png.py`. |
| Sprite source | Exists | `get_def` over `lod()` (`renderers/sprites.py:223`). |

### What the code has that the design lacks

- **Border sealing.** A missed concept. It is now Border seam in section 2.
- **Portal rescue.** `rescue_unreachable_zones` (`portal/geometry.py:259`) turns a zone cut off on foot into a reward zone behind a guarded monolith pair. It repairs what Geography and Scenery broke. Decision 3.
- **Sealed treasure zones.** `GatedStep` and `TreasureStep` put small one-passage zones behind a border gate or monolith and fill them. The problem does not ask for them. Decision 3.
- **Seer-hut quests.** `place_seer_hut_quests` in `steps/loot/step.py` places quests, which the problem puts out of scope. Waste. Decision 4.
- **Walled-pocket check.** `vegetation/step.py:33-51` raises when scenery walls in a pocket. It is a reachability check inside Scenery. It moves to the reachability verdict.
- **Shared workspace and provider registry.** `pipeline.py:59-165`. Waste against claim 12's verdict. Parked, decision 6.

### Claims

| Claim | In the code | In the design |
|---|---|---|
| 1. Capacity-constrained growth | Present (`macro_topo.py:383`), then overwritten by flood fill | Kept for Zone shape |
| 2. Corpus transitions | Present | Kept |
| 3. Gibbs process | Present as the vegetation sampler | Kept as Stand |
| 4. Walkable web | Present, and it imports Population | Kept as Open way, without the imports |
| 5. Gameplay after vegetation | Present, with named town room | Open, decision 1 |
| 6. Loot scatter and pockets | Present across three steps | Split. Scatter lies over the open field, not along routes, so "along routes" is already gone |
| 7. Gates in the macro layout | Absent. The gate step picks the link | Rejected as stated. Level link goes to Geography |
| 8. Sawmill and ore pit | Present as `ECONOMY` in `draw.py` | Kept inside Start town |
| 9. One ontology | Present | Kept |
| 10. Masks from the table | Present | Kept |
| 11. Flood-fill zones | Present, also on generated maps | Kept for real maps only |
| 12. Pipeline with shared workspace | Present | Sequence kept, workspace dropped |
| 13. Terrain rule on add | Present, split across two modules and a caller protocol | Kept as one Standing rule |
| 14. Priors as data | Present, four caches | Kept as one Convention book |
| 15. Random classes | Present | Kept inside Zone budget |

### Open lookups, resolved

1. **The four measures.** `corpus_match.py` computes them, for corpus and generated zones, as a report. No verdict exists.
2. **Run time.** A full size-72 run of seed 3 took 78 to 86 seconds. A run stopped after zone reading took 58 seconds. Other jobs shared the machine, so the split is rough. The done criterion is 20 seconds, so a developer waits four times too long. Decision 5.
3. **Checks on add.** Terrain and visitable coverage are both checked, by two modules, with rules the caller supplies.
4. **Reachability.** A check exists mid-generation and raises. It misses start towns other than one, and everything placed after it. A repair step runs before it.
5. **Seed stream.** About 23 draws use ad hoc salts. `steps/treasure/fill.py:284` and `steps/gated/placer.py:327` use the same expression, so two steps draw the same stream. `steps/loot/caches.py:655` and `steps/scatter/scatter.py:79` share a salt. `markov.py:173` ignores the seed. `gameplay/step.py:315` uses `seed + level`.
6. **Worth.** It does not exist. Each guard rule invents its own strength.
7. **Corpus numbers.** Four caches with four staleness rules, as in the Convention book row.
8. **Shared state.** `PlacementWorkspace`, `LevelWorkspace`, `ZoneWorkspace` and `ProviderRegistry` carry about 20 mutable fields between steps. `models/AGENTS.md` already names zones on the Map as known debt.

## 6. Slices

Each slice runs from the request to a file a person can open and a verdict they can read.

1. **Walking skeleton: a seed gives the same openable map twice.** Touches Seed stream,
   Zone plan, Start town, Roster, Map file, Reachability verdict. Done when two runs of
   one seed give byte-identical `.vmap` files, the editor opens the file, a two-player game
   starts, and the verdict walks from every start town and passes. This slice fixes the
   zip timestamps, the per-part seed substreams and the one-town-per-zone rule.
2. **The map is judged against the corpus.** Touches Convention book, Placement measure,
   Spread verdict, Standing audit. Done when one command prints, for seeds 1 to 3 at size
   72, a pass or fail per object type and measure, read from one cache keyed to the
   corpus.
3. **Zones cross only at passages.** Touches Zone shape, Passage, Border seam, Open way,
   Reachability verdict. Done when generated zones keep their planned labels, Scenery
   imports nothing from Population, and a seed sweep needs no portal rescue.
4. **Objects settle like a mapmaker's.** Touches Site, Worth, Guard, Zone budget. Done
   when back contact is a scored term, every guard reads a worth, and the spread verdict
   passes for back contact and the mine guard share.
5. **A developer sees one part in under 20 seconds.** Touches every stage's stop point and
   the Convention book. Done when a size-72 run stopped after any part finishes in under
   20 seconds on the developer's machine.

## 7. Open decisions

1. **Does gameplay settle into finished scenery, or does scenery grow around sites?**
   Options: scenery first with clearings of a requested size; sites first with scenery
   around them; both interleaved per zone. Recommendation: scenery first, with Zone budget
   asking Clearing for sizes and never for a town. Reason: the back-contact and overlap
   rates measure objects pushed into existing scenery, and the code already works this way.
2. **What happens when the reachability verdict fails?** Options: fail with the seed and
   the cut-off object; retry on the next substream; repair with a portal. Recommendation:
   fail with the seed. Reason: a repair hides the Geography or Scenery bug that cut the
   zone off, and slice 3 removes the cause.
3. **Do portal rescue and sealed treasure zones stay?** Options: keep both as Crossing
   and a new Treasure room concept; drop both; drop the rescue and measure sealed zones in
   the corpus first. Recommendation: drop the rescue and measure first. Reason: the rescue
   repairs a bug, while a sealed zone may be a real convention the problem did not name.
4. **Do seer-hut quests stay?** Options: remove them; move quests into scope.
   Recommendation: remove them from v2. Reason: the problem puts quests out of scope.
5. **Mines: all guarded, or 64%?** Options: keep every mine guarded, as a comment in
   `mines.py:166-167` records a user bug report; draw the corpus 64%. Recommendation: draw
   64%. Reason: the problem statement names 64% as a hand-made convention, and it is the
   newer instruction.
6. **Parked for `target-architecture`.** Removing `PlacementWorkspace` and
   `ProviderRegistry`; one owner for the seed streams; one Convention book; `zone_plan.py`
   importing Population; zones on the Map; two reachability walkers; the standing rule
   split across `validate.py`, `map_state.py` and step pre-checks. Recommendation: run
   `target-architecture` on these before slice 3. Reason: each crosses more than the parts
   this note changes.
7. **Where does the time go?** Options: profile a size-72 run per part first; cache zone
   reading; move stats mining out of generation. Recommendation: profile first. Reason:
   the one split measured here ran beside other jobs, and 58 of about 80 seconds before
   scenery is too rough to act on.
