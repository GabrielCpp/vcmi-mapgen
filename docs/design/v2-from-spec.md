# v2 from spec: a VCMI map generator, decomposed top-down

Input: `docs/specs/pp-map-generator-solution.md`, an as-built spec. It is a solution, so
section 1 extracts the problem from it and section 1b lists its design decisions as claims.

**Disclosure: the existing solution leaked in before section 5.** An earlier version of the
decompose skill allowed `README.md`, `AGENTS.md` and the skills. I read `README.md`, the
`vcmi-mapgen-maps` skill and the memory note on placing gameplay after vegetation before the
skill changed to forbid them. The root `AGENTS.md` was in context from the start. So I knew
the repo has a pipeline of steps, a segmentation module, a walkable web built in a zone plan,
and a settled but unbuilt decision to place gameplay after vegetation. Each part and concept
below passes the test "would I have named this without having seen the solution?" with two
exceptions, flagged where they occur. The spec itself names its layers, and four of the seven
parts line up with them. I kept that split because a mapmaker would draw the same lines.

## 1. Problem

A Heroes III player who wants a new map to play must build one by hand in the editor, or
accept a template map that looks nothing like the maps people make. Neither gives a map that
looks and plays like the 159 hand-made maps in the corpus.

Done, for that player:

- One integer seed, a size and a player count give a map the VCMI editor opens with no
  warning, and that a game can start on at once.
- Each of the N players starts owning a town, in N regions spread across the map. Players sit
  in the requested teams. Victory is "defeat all enemies".
- Every town, mine, dwelling, visitable and pickup is reachable over land from the rest of
  its landmass, on every seed tried. A hero may have to fight a guard to get there.
- Every mine is guarded. Every start town has a sawmill and an ore pit within about 7 tiles.
  The map holds at least one mine of each of the six basic resources. Gold mines number at
  most one fewer than towns.
- The map looks hand-made: a handful of large regions, not a patchwork. Scenery covers each
  region's blocked share within a few points of the corpus rate (about 0.5 on grass). Region
  borders stay at least as open as the corpus borders (0.39 to 0.54 of the contact front).
- The same seed gives a byte-identical map file.
- A picture of the map, drawn with the real game sprites, shows what the editor will show.

Out of scope:

- An underground level and its two-level gates. The spec builds one surface only.
- Roads, rivers, placed heroes, quests and portal chains.
- Fair starts beyond spreading players apart. No mirroring of start-region value.
- A fitted model of guard strength against guarded value. Heuristic level bands stay.
- Scoring generated maps against corpus acceptance bands.
- Reading the `.h3m` corpus into editor files, and building the object catalogue from the
  editor's object table. Both are inputs here.
- Copying maps into the game's map folder.

### 1b. Claims

In the spec's words, one per line.

1. Learn statistics from the corpus; take identities from the ontology.
2. Fit models where the corpus has signal; use explicit rules where it doesn't.
3. Reachability is guaranteed by construction (a protected walkable web that vegetation may
   never block) and then verified by a map-level gate (G2) with a repair fallback.
4. Every RNG is `random.Random(seed ^ zone-specific-constant)`.
5. Most placed objects are the editor's RANDOM classes (town 70 %, dwelling 80 %, resource
   pile 60 %, reward pickup 45 %, guard 100 %).
6. Stage order: macro terrain, tiling, segmentation, then per land zone gameplay (L3), the
   protected web, vegetation (L2), pickups (L4), then water, guard dedupe, G2, render,
   export, playability.
7. Plan macro structure first; use the Markov chain only for border texture, in a `BAND=2`
   tile band around zone borders.
8. Zone target areas are drawn from the corpus area distribution and rescaled to exactly fill
   the land budget (floor `MIN_ZONE_AREA=40`).
9. Terrains are assigned by Metropolis on the seed k-NN graph with energy −log A[tᵢ][tⱼ].
10. Grow zones by capacity-constrained multi-source Dijkstra with jittered edge costs
    (`JITTER=1.4`).
11. Water mask: low-frequency value noise thresholded at the water-fraction quantile, with
    modes none, normal and islands.
12. Water and rock are segmentation barriers, never zones.
13. Placement anchors are sampled from a per-purpose log-linear intensity over edge-distance
    and gate-distance bins (plus openness for pickups), a counting fit clipped at ±2, 80
    anchors with a 25-step spiral nudge.
14. Counts are `stoch(density × area, scaled_cap)`, with area-scaled soft caps; a town needs
    `area ≥ 150`.
15. Fixed identities are weighted by corpus frequency, square-root damped with a 20× penalty
    for repeats within a zone.
16. A town zone gets a sawmill and ore pit next to the town; further mines are distinct
    types; a map-level ledger covers all six basic resources; gold only while
    `gold_placed < towns − 1`.
17. Vegetation is attracted to the mines: `+ATTRACT=0.7` in a Chebyshev-3 annulus.
18. Gameplay objects are rigid: full footprint in-zone, `GAP=2` from every other gameplay
    footprint, own approach in-zone and standable.
19. Mine guards sit on the mine's approach tile unconditionally, level from resource rarity;
    the other approach-grid tiles are sealed with single-cell blocking decorations.
20. Gate guards stand at each band's narrowest tile with probability 0.65, level
    `min(7, 1 + area//250 (+1 @ 40 %))`.
21. Corridor dedupe: any two GUARDs within Chebyshev 2 keep only the stronger.
22. Gate bands: `max(3, round(open_frac × front_len))` tiles of each contact front are
    protected.
23. The web: farthest-point nodes, every gate-band representative and every gameplay approach
    tile, joined by geodesic paths into a spanning tree; a hard zero for vegetation.
24. Vegetation is a Gibbs marked point process: birth/death Metropolis-Hastings, log-Gaussian
    Cox modulation times a Geyer-saturated pair potential, coverage steered by a global
    offset; footprints may stack.
25. Pickups run over the finished open field: guarded caches in pockets with a narrow mouth,
    guard on the mouth, level from cache value; unguarded scatter is mostly fixed loot.
26. Water is mined and populated as raw connected components; bodies ≥ 25 tiles; no random
    artifacts on water.
27. A shipyard goes on the shore with probability `min(0.8, dens × area × 3)`.
28. G2: 8-connected BFS over open land; up to 6 repair rounds carve vegetation only; targets
    on other islands do not abort.
29. Player zones by greedy max-min centroid distance; a forced town sits at the zone centroid
    by an exhaustive nearest-first scan.
30. Playability is a post-export patch of the `.vmap`; town ownership lives on the town
    object.
31. The stats file is versioned; a mismatch triggers a re-mine.
32. `--install` copies `.vmap`s into the VCMI `Maps/pp-gen/` folder.

## 2. Parts and concepts

### Level 1: parts

| Part | Owns | Never knows | Hands to |
|---|---|---|---|
| Corpus statistics | How much of each thing real maps hold, and where they put it | Any generated map or seed | Every other part except Delivery, as fitted numbers |
| Land | Which terrain each tile has, and which regions and water bodies that makes | Any object | Regions, borders and water bodies to Holdings, Passage, Scenery, Loot and guards |
| Holdings | The buildings a player owns or visits: towns, mines, dwellings, banks, shrines, shipyards | How scenery is sampled, and what a pickup holds | Placed buildings and their entrances to Passage, Scenery, Loot and guards |
| Passage | Which tiles must stay walkable, and proof that the finished map is walkable | What a building or pickup is worth | The keep-clear tiles to Scenery. The verdict to Delivery |
| Scenery | Where impassable trees, rocks and lakes stand | What any building is, beyond its footprint | The finished open field to Loot and guards |
| Loot and guards | Pickups on land and water, and the monsters that guard buildings, passages and caches | How scenery was sampled | Pickups and guards to Passage and Delivery |
| Delivery | The map file the editor opens, its players and teams, and the picture | How anything was chosen | The file and the picture to the player |

Flow. Corpus statistics runs once, offline, and every generation reads its numbers. Land
turns the seed into terrain, regions and water bodies. Holdings places buildings region by
region. Passage opens the region borders and joins every building entrance into a walkable
network, then hands Scenery the tiles it must leave clear. Scenery fills the rest. Loot and
guards places pickups into the open field that is left, and posts guards. Passage then checks
the finished map. Delivery writes the file and draws the picture.

One paragraph, no jargon: the generator first studies real maps. It then draws the land,
builds the towns and mines, keeps roads open between them, plants forests and mountains
around them, scatters treasure and monsters, checks a hero can walk everywhere, and saves the
map.

Shared value types, owned by no part:

- **Object kind**: the catalogue entry for one object, with its identity, footprint,
  entrance, allowed terrains and category. The object catalogue is an input.
- **Region**, **Border** and **Water body**: produced by Land, read by four parts. Border is
  the contact front between two regions. Holdings measures gate distance from it, Passage
  opens it, and Loot and guards guards it.
- **Placed object**: an object kind at a position.
- **Random stream**: a seeded stream of draws, derived from the seed and a salt.
- **Request**: seed, size, water mode, player count, teams, and which outputs to write.

Corpus statistics also needs Land's segmentation rule to find regions in real maps. That is
one rule used on two inputs, so it lives once, in Land.

### Level 2: concepts

**Corpus statistics** (7)

| Concept | Owns | Never knows |
|---|---|---|
| Corpus | The real maps as terrain and catalogue objects | Any statistic |
| Land statistics | Region area distribution, terrain shares, terrain adjacency, water share, border texture conditionals | Objects |
| Placement tendency | Per terrain and purpose: density, counts per covariate bin, tiles per bin, guarded share, border open share | How a sampler uses the counts |
| Intensity fit | The relative intensity of each covariate bin, from counts and exposure | Which purpose or terrain it fits |
| Scenery statistics | Per terrain: intensity by rim distance, pair correlation by ring, sprite mix, blocked share, overdispersion | Buildings |
| Water density | Per purpose density over water tiles | Regions |
| Statistics store | Whether stored statistics match the current schema | How any statistic is computed |

**Land** (7)

| Concept | Owns | Never knows |
|---|---|---|
| Water plan | Which tiles are sea, for a water mode | Regions |
| Region plan | How many regions, their target areas and their seed points | Terrain types |
| Terrain assignment | One terrain per planned region, from adjacency preferences | Region shapes |
| Region growth | Which tiles each planned region claims | Terrain types |
| Border texture | Corpus-like terrain transitions near borders | Region interiors |
| Tile view | A valid transition sprite on every tile, which rules out patches too thin for any sprite | Regions |
| Segmentation | Splitting a terrain grid into regions, borders and water bodies | Where the grid came from |

**Holdings** (6)

| Concept | Owns | Never knows |
|---|---|---|
| Object budget | How many buildings of each purpose a region gets | Where they go |
| Placement field | How likely each tile of a region is to host a purpose | The count |
| Identity choice | Which concrete or random object fills a purpose | Where it stands |
| Economy ledger | Which mine types the map still lacks, and the gold ration | Region geometry |
| Site rule | Whether an object may stand on a spot | Why the spot was proposed |
| Start region | Which regions host players, and their anchor point | Teams |

**Passage** (4)

| Concept | Owns | Never knows |
|---|---|---|
| Gate band | The stretch of a border that must stay open | What lies behind it |
| Route web | A walkable tree joining a region's interior, its gate bands and every entrance, shore landings included | Scenery statistics |
| Keep-clear set | The union of tiles Scenery may not block | How each tile got there |
| Reachability check | Whether every target on a landmass is reachable in the finished map | How the map was built |

**Scenery** (5)

| Concept | Owns | Never knows |
|---|---|---|
| Scenery process | Proposing and accepting births and deaths of scenery objects | Which terms make up the intensity |
| Clustering field | Large-scale forest and clearing variation | Neighbours |
| Neighbour interaction | Local attraction and repulsion between nearby scenery | Large-scale variation |
| Coverage steering | The global offset that brings blocked share to target | Local structure |
| Mark choice | Which sprite fills a scenery category | Position |

**Loot and guards** (6)

| Concept | Owns | Never knows |
|---|---|---|
| Guard strength | A guard's level from the value it guards | Where it stands |
| Guard post | Where a guard stands so it cannot be walked around | Its level |
| Pocket | A dead end with a narrow mouth, deep from the route web | What goes in it |
| Cache | The contents of a pocket | Pocket geometry |
| Scatter | Unguarded pickups along routes | Pockets |
| Water loot | Pickups, boats, whirlpools and sea guards on a water body | Land regions |

Guard post covers mine approaches, passage chokepoints, cache mouths, roaming spots and sea
spots. It also seals the side tiles of a mine approach. That is one responsibility: the post
cannot be bypassed.

**Delivery** (4)

| Concept | Owns | Never knows |
|---|---|---|
| Map file | The editor document: terrain, views, objects with full identity and visit directions | The scenario rules |
| Scenario | Player slots, their start towns and owners, teams, victory and defeat | File layout |
| Team layout | Reading "ffa", "2v2" or "0,0,1,1" into a team per player | Player slots |
| Picture | Drawing the map with the game's own sprites | The file |

## 3. Invariants

| # | Invariant | Part: concept |
|---|---|---|
| 1 | Every random draw comes from a stream derived from the seed and a salt for its part and region or water body. Order of regions never changes a draw. | Shared: Random stream |
| 2 | The same request gives a byte-identical file. Nothing in the file depends on set or dict order. | Delivery: Map file |
| 3 | An object's identity, footprint, entrance and terrains come from the catalogue, never from the corpus. | Corpus statistics: Corpus |
| 4 | Stored statistics from an older schema are never used. | Corpus statistics: Statistics store |
| 5 | Water and rock are never regions. | Land: Segmentation |
| 6 | Planned region areas follow the corpus distribution and fill the land. No region is under 40 tiles. | Land: Region plan |
| 7 | Neighbouring regions never share a terrain. | Land: Terrain assignment |
| 8 | Border texture changes no tile more than 2 tiles from a border. | Land: Border texture |
| 9 | Building footprints lie inside their region, never overlap, and keep a 2-tile gap. Each entrance is standable. No footprint cuts off part of the walkable area around it. | Holdings: Site rule |
| 10 | Every basic resource has a mine somewhere on the map. Gold mines number at most towns minus one. Every town region holds a sawmill and an ore pit near its town. | Holdings: Economy ledger |
| 11 | Each start region holds a town at its anchor point. | Holdings: Start region |
| 12 | Each gate band covers at least max(3, corpus open share × front length) tiles. | Passage: Gate band |
| 13 | No blocking scenery cell covers a keep-clear tile. | Scenery: Scenery process |
| 14 | In the finished map, every entrance and pickup is reachable over land from every other on its landmass, guards counting as passable. | Passage: Reachability check |
| 15 | Every mine has a guard on its entrance, and no other approach tile is open. | Loot and guards: Guard post |
| 16 | Each passage holds at most one guard. | Loot and guards: Guard post |
| 17 | A guard's level is a function of what it guards. | Loot and guards: Guard strength |
| 18 | No random artifact is placed on water. | Loot and guards: Water loot |
| 19 | Each player slot names a town object that player owns. | Delivery: Scenario |
| 20 | Every visitable object in the file carries its visit directions. | Delivery: Map file |
| 21 | Every island of at least 50 tiles, and every sea of at least 50 tiles, has a shipyard on its shore. | Holdings: Object budget |
| 22 | No terrain patch is thinner than the smallest patch a transition sprite can draw. | Land: Tile view |

## 4. Forces and patterns

### Forces

- F1. Reading 159 maps is slow and the corpus rarely changes. Generation must stay cheap.
- F2. Statistics vary by terrain and by purpose. The machinery that uses them does not.
- F3. The corpus is noisy and map-specific. The catalogue is the game's truth.
- F4. Per-terrain counts are small, and fits must be deterministic.
- F5. Each part depends on the previous part's finished product. Scenery needs the entrances
  to keep clear. Loot needs the finished open field.
- F6. Tests assert determinism and legality part by part, so each part must run alone on a
  given input.
- F7. The scenery intensity is a product of independent terms: rim distance, clustering,
  neighbours, coverage and, in the spec, attraction to mines. Terms were added over time and
  are tested alone.
- F8. A purely attractive pair process explodes. Corpus log g(r) is above zero at every range.
- F9. The game's sprites live in a local install that may be absent in a test or on CI.
- F10. Guards differ by what they guard: mine, passage, cache, roaming, sea. The spec lists
  five, and each has its own post rule and level rule.
- F11. Three water modes differ only by numbers.
- F12. Two regions share one border. Both see the same passage.
- F13. The corpus gate-distance histogram for guards is flat, while players expect guarded
  passages.
- F14. Real maps set buildings against scenery. The spec answers it by pulling scenery toward
  mines. The memory note records corpus overlap rates (towns 92 %, mines 61 %). That source
  is one I should not have read before section 5.

### Between parts

- **A sequence of stages with a typed product per part** (F5, F6). Land hands regions,
  Holdings hands placed buildings, Passage hands the keep-clear set, Scenery hands the open
  field, Loot and guards hands pickups and guards. A single mutable map handed along would
  meet F5 too, but F6 wants each part's input to be a value a test can build.
- **Statistics as stored data, read by name** (F1). The Statistics store is a cache keyed by
  schema version.
- **The sprite source as a port with one real adapter** (F9). The Picture reads sprites
  through it. A test supplies none and skips.

### Inside the parts

| Concept | Pattern | Force |
|---|---|---|
| Statistics store | Cache keyed by schema version | F1 |
| Placement tendency, Scenery statistics, Water density | Plain values keyed by terrain and purpose | F2 |
| Intensity fit | Plain function: smoothed log ratio, clipped | F4 |
| Corpus | Plain function that resolves every object through the catalogue | F3 |
| Land concepts | Plain functions. The water mode is a dict of numbers | F11 |
| Object budget, Identity choice, Economy ledger | Plain functions over the fitted values | F2 |
| Site rule | One function with early returns | Force weak: five rules, none swapped |
| Placement field | Plain function over Intensity fit | F2 |
| Scenery intensity | Weighted sum, in log space, of term functions | F7 |
| Clustering field and Neighbour interaction | Two scales, the pair term saturated | F8 |
| Guard post and Guard strength | A dict from guarded kind to its post rule and level rule | F10 |
| Guard on a passage | Posted once per border, by the border's owner | F12 |
| Gate guard placement | An explicit rule, not a fit | F13 |
| Scenario | A plain value the Map file writes | No force for a separate patch |
| Everything else | Plain function or value | None |

### Claims

| Claim | Verdict | Reason |
|---|---|---|
| 1 | Re-derived | F3. Invariant 3 |
| 2 | Re-derived | F4 and F13 |
| 3 | Re-derived, repair rejected | Construction plus check meets invariant 14. The spec says repair never fires, so no force keeps it. Open decision 2 |
| 4 | Re-derived, changed | Invariant 1. The salt names the part and the region, not only the region |
| 5 | Re-derived | Domain convention, and the only way to scale guard level without a creature table |
| 6 | Partly re-derived | F5 forces entrances before the keep-clear set, and the open field before loot. Placing buildings before scenery is not forced. Open decision 1 |
| 7, 8, 10, 11 | Re-derived | Done-when: a handful of large regions |
| 9 | Re-derived | Invariant 7 |
| 12 | Re-derived | Invariant 5 |
| 13, 14, 15 | Re-derived | F2, F4. Rare visitables never appeared without damping |
| 16 | Re-derived | Done-when economy |
| 17 | Pending | Depends on open decision 1 |
| 18 | Re-derived | Corpus maps do not pack buildings wall to wall |
| 19, 20 | Re-derived | Invariants 15, 17. F13 |
| 21 | Rejected | F12. One guard posted per border makes the dedupe unnecessary |
| 22, 23 | Re-derived | Invariants 12, 13, 14 |
| 24 | Re-derived | F7, F8 |
| 25, 26 | Re-derived | Done-when and invariant 18 |
| 27 | Re-derived, extended | The chance stays for mainland shores. Invariant 21 forces a shipyard where a hero would otherwise be stranded |
| 28 | Check re-derived, repair rejected | See claim 3 |
| 29 | Re-derived | Clustered starts. Invariant 11 |
| 30 | Ownership fact kept, patch rejected | No second writer to protect in this design |
| 31 | Re-derived | F1 and invariant 4 |
| 32 | Rejected | Out of scope |

### Open lookups

| # | Fact needed from the existing system | Decision waiting on it |
|---|---|---|
| L1 | Which of the seven parts exist, and where | Every verdict in section 5 |
| L2 | Whether buildings are placed before or after scenery | Open decision 1, claims 6 and 17 |
| L3 | Whether passage guards are posted per border or per region, and whether a dedupe exists | Claim 21 |
| L4 | Whether a repair exists and whether it ever fires | Open decision 2 |
| L5 | Whether the scenario is written with the file or patched after | Claim 30 |
| L6 | Whether an underground level exists | Scope |
| L7 | Where stored statistics live, and whether they carry a version | Invariant 4 |
| L8 | Whether the catalogue gives random classes by level and pools by purpose | Identity choice, Guard strength |

## 5. Mapping onto the existing system

Paths are relative to `vcmi_mapgen/`.

### Parts

| Part | Verdict | Where | Finding |
|---|---|---|---|
| Corpus statistics | Reshape | `steps/terrain_gen/macro_topo.py:132`, `steps/gameplay/mines.py:36`, `steps/gate/gates.py:141`, `steps/vegetation/stats.py` | No part exists. Each step mines its own statistics on first use and caches them in `data/pp/`. The design is right: F1 wants one offline run, and a step that may read the whole corpus mid-generation cannot run alone on a given input (F6). Parked as decision 6 |
| Land | Exists | `steps/terrain_gen/step.py:133`, `steps/terrain_gen/macro_topo.py`, `kit/tiling.py`, `kit/terrain_segment.py:202` | Owns and never-knows match. The code also builds an underground level, which is out of scope |
| Holdings | Reshape | `steps/gameplay/step.py:168` | The code places buildings after scenery, against the scenery (`steps/gameplay/step.py` docstring). Start region lives in the scenery step (`steps/vegetation/step.py:100`). Decision 1 |
| Passage | Reshape | `kit/topology.py:170`, `steps/zone_plan.py:195`, `steps/vegetation/sample.py:195`, `steps/border/step.py:1` | The largest mismatch. The code keeps regions isolated, with one or two 3-tile entrances per border (`kit/topology.py:15-18`). Scenery grows a ridge along every border (`steps/vegetation/sample.py:269`), and a later stage closes the rest of the border (`steps/border/step.py:1`). No map-level reachability check runs. Decisions 2 and 3 |
| Scenery | Exists | `steps/vegetation/sample.py:293` | The sampler matches. Its step also plans the regions' entrances, builds the route web, picks start regions, populates water and seals borders (`steps/vegetation/step.py:99-168`). That is the work of three other parts in one step. Parked as decision 6 |
| Loot and guards | Reshape | `steps/loot/caches.py:315`, `steps/scatter/scatter.py:64`, `steps/border/entrances.py:81`, `steps/gameplay/water.py:139` | Guard posts and guard levels are split across three steps with three level rules. Water loot runs inside the scenery step through `steps/zone_plan.py:172` |
| Delivery | Exists | `renderers/vmap.py:28`, `renderers/png.py` | Owns and never-knows match. The header source breaks invariant 2. Decision 5 |

### Concepts

| Part: concept | Verdict | Where | Finding |
|---|---|---|---|
| Corpus statistics: Corpus | Exists | `kit/objects.py:35`, `load_faithful` | Identity comes from the ontology, as invariant 3 asks |
| Corpus statistics: Land statistics | Exists | `steps/terrain_gen/macro_topo.py:58`, `steps/terrain_gen/markov.py:30` | Matches |
| Corpus statistics: Placement tendency | Exists | `steps/gameplay/mines.py:36`, `steps/gate/gates.py:141` | Split over two files by purpose. Not traced further |
| Corpus statistics: Intensity fit | Exists | `steps/gameplay/mines.py` | Not traced to a line |
| Corpus statistics: Scenery statistics | Exists | `steps/vegetation/stats.py` | Stored per terrain in `data/pp/veg_<terrain>.json` |
| Corpus statistics: Water density | Exists | `steps/gameplay/water.py` | Not traced to a line |
| Corpus statistics: Statistics store | Reshape | `steps/gameplay/mines.py:38`, `steps/gate/gates.py:21`, `steps/terrain_gen/macro_topo.py:139`, `steps/vegetation/stats.py` | Gameplay and gate statistics carry a version. Land statistics are reused whenever the file exists, and scenery statistics carry no version. Invariant 4 holds for two of four stores. The code is wrong |
| Land: Water plan | Exists | `steps/terrain_gen/macro_topo.py:179` | Matches |
| Land: Region plan | Exists | `steps/terrain_gen/macro_topo.py:307`, `:499` | Matches |
| Land: Terrain assignment | Exists | `steps/terrain_gen/macro_topo.py:340` | Matches |
| Land: Region growth | Exists | `steps/terrain_gen/macro_topo.py:383` | Matches |
| Land: Border texture | Exists | `steps/terrain_gen/macro_topo.py:432`, `:451` | Matches |
| Land: Tile view | Exists | `kit/tiling.py:263`, `kit/tiling.py:238` | The code removes patches too thin to tile before it picks sprites. The design had missed that rule. Section 2 and invariant 22 now carry it |
| Land: Segmentation | Exists | `kit/terrain_segment.py:202` | Matches |
| Holdings: Object budget | Reshape | `steps/gameplay/draw.py` | The code draws one total per region at the corpus rate and counts forced objects inside it. The concept holds. Claim 14 does not. Forced seaports at `steps/gameplay/water.py:31-34` and `:195` match invariant 21 |
| Holdings: Placement field | Reshape | `steps/gameplay/site.py` | The code scores contact with scenery behind the building, not an intensity over edge and gate distance. This follows from decision 1 |
| Holdings: Identity choice | Exists | `steps/gameplay/draw.py:131`, `steps/gameplay/mines.py:165` | Weight is `w ** 0.5 + 0.3`, a square-root damping with a floor |
| Holdings: Economy ledger | Exists | `steps/gameplay/mines.py:543`, `:565` | Matches invariant 10 |
| Holdings: Site rule | Exists | `steps/gameplay/site.py` | Blocking cells may cover the route web, and a footprint may not split a walkable area. The design had missed the second rule. Invariant 9 now carries it |
| Holdings: Start region | Reshape | `steps/gameplay/mines.py:655`, `steps/zone_plan.py:278`, `steps/vegetation/step.py:100` | The scenery step calls it, and it reserves room for each start town before scenery (`steps/zone_plan.py:248`). The `--players` help says "the N largest zones get start towns" (`cli.py:295`), which the greedy spread contradicts |
| Passage: Gate band | Reshape | `kit/topology.py:170`, `kit/topology.py:15-18`, `steps/vegetation/sample.py:236`, `steps/scatter/scatter.py:60` | The code has two gate bands. The route web protects a corpus-wide band, and the entrance plan keeps one or two 3-tile bands that the border closure leaves open. On a 20-tile front at open share 0.39, invariant 12 asks for 8 tiles and the code keeps 3 or 6. Two concepts enforce one invariant, and they have drifted. Decision 3 |
| Passage: Route web | Exists | `steps/vegetation/sample.py:195`, `steps/zone_plan.py:63` | Built before buildings, so it cannot join their entrances. The site rule makes buildings leave the web walkable instead. Decision 1 |
| Passage: Keep-clear set | Reshape | `steps/zone_plan.py:236`, `steps/border/step.py:70` | Spread over several workspace fields (`hard_avoid`, `seal_avoid`, `ridge`) that each stage reads and extends. No single union exists |
| Passage: Reachability check | Reshape | `kit/reachability.py`, `steps/vegetation/step.py:33` | The check exists but only a test calls it. The pipeline checks each level for walled-off pockets before loot, and raises. Nothing checks the finished map, so invariant 14 is a wish. The code is wrong. Decision 2 |
| Scenery: Scenery process | Exists | `steps/vegetation/sample.py:293`, `:326` | Matches |
| Scenery: Clustering field | Exists | `steps/vegetation/sample.py:64` | Matches |
| Scenery: Neighbour interaction | Exists | `steps/vegetation/sample.py:60-63` | Matches, saturated at 2 |
| Scenery: Coverage steering | Exists | `steps/vegetation/sample.py:269-278` | Matches. The same block adds a border term that multiplies intensity about 12 times on border tiles. That term serves isolation. Decision 3 |
| Scenery: Mark choice | Exists | `steps/vegetation/sample.py:66` | Matches |
| Loot and guards: Guard strength | Reshape | `steps/gameplay/mines.py:170`, `steps/border/entrances.py:30`, `steps/loot/caches.py` | Three rules in three steps. The mine rule sets sawmill and ore pit to level 1, and the spec says 3. The passage rule divides area by 200, and the spec says 250. Decision 4 |
| Loot and guards: Guard post | Reshape | `steps/border/entrances.py:81`, `steps/loot/caches.py:381`, `steps/placement.py:139` | Posts are spread over the step that owns each guarded object. A spacing rule keeps guards 2 apart, so no dedupe runs. Passage guards are posted per entrance, which matches the design's "one per border" |
| Loot and guards: Pocket | Exists | `steps/loot/caches.py:198`, `kit/topology.py:23` | Matches |
| Loot and guards: Cache | Exists | `steps/loot/caches.py:413` | Matches |
| Loot and guards: Scatter | Exists | `steps/scatter/scatter.py:64` | Matches |
| Loot and guards: Water loot | Reshape | `steps/gameplay/water.py:139`, `steps/zone_plan.py:172` | The scenery step populates water. Parked as decision 6 |
| Delivery: Map file | Reshape | `renderers/vmap.py:17-25` | The header comes from the first `.vmap` a directory glob returns in the local install, else from the static template. Glob order is not sorted, and the install varies by machine. The same seed can give different bytes. The code is wrong. Decision 5 |
| Delivery: Scenario | Exists | `renderers/vmap.py:54`, `:167` | Applied to the in-memory document before the write. Ownership sits on the town object |
| Delivery: Team layout | Exists | `renderers/vmap.py:152` | Matches |
| Delivery: Picture | Exists | `renderers/png.py`, `renderers/sprites.py` | Reads sprites from the local install. Tests skip without it, as F9 asks |

### What the existing system has that the design lacks

| Extra | Where | Verdict |
|---|---|---|
| Underground level and two-level gate pairs | `steps/terrain_gen/step.py:116`, `steps/gameplay/gate_pairs.py` | Waste for this problem, which is out of scope. Decision 7 |
| Sealed small regions behind a border gate or monolith pair | `steps/gated/step.py:35` | Waste for this problem. It answers isolation. Decision 7 |
| Treasure filling of sealed regions | `steps/treasure/step.py:17` | Waste for this problem. It depends on sealed regions |
| Closing every border outside the entrances | `steps/border/step.py:60` | Waste if decision 3 goes to open bands. It breaks invariant 12 today |
| Portal pairs from cut-off regions to the start region | `steps/portal/step.py:53` | Waste if decision 3 goes to open bands. It repairs isolation after the fact |
| Seer-hut quests | `steps/loot/caches.py:793` | Waste for this problem, which is out of scope. Decision 7 |
| Removing patches too thin to tile | `kit/tiling.py:238` | Missed concept. Folded into Tile view, invariant 22 |
| Forced seaports on islands and seas | `steps/gameplay/water.py:195` | Missed concept. Invariant 21 |
| Shore landings joined to the web | `steps/zone_plan.py:117`, `:63` | Missed concept. Route web now names them |
| Room reserved for start towns before scenery | `steps/zone_plan.py:248` | Missed concept, needed only if decision 1 goes to "after". Decision 1 |
| Debug overlays, ontology catalogue render, corpus match report | `renderers/overlays/`, `renderers/ontology_render.py`, `corpus_match.py` | Neither. Developer tools outside the player's problem |

### Claims

| Claim | Existing system | Design |
|---|---|---|
| 1 | Follows | Follows |
| 2 | Follows | Follows |
| 3 | Construction only. No map-level check and no repair | Construction and check, no repair |
| 4 | Not checked beyond the draw salt (`steps/gameplay/draw.py`) | Follows, salt per part and region |
| 5 | Follows for towns (`steps/gameplay/mines.py:165`). Others not checked | Follows |
| 6 | Does not. Order is terrain, segmentation, scenery, buildings, sealed regions, treasure, border closure, portals, caches, scatter (`cli.py:174`) | Pending decision 1 |
| 7, 8, 9, 10, 11, 12 | Follows | Follows |
| 13 | Does not for buildings. They score contact with scenery | Pending decision 1 |
| 14 | Does not. One total per region with forced objects inside | Budget per purpose, either form |
| 15 | Follows, with a floor of 0.3 | Follows |
| 16 | Follows (`steps/gameplay/mines.py:565`) | Follows |
| 17 | Does not. No attraction term exists | Pending decision 1 |
| 18 | Partly. Blocking cells may cover the web and the rim | Follows |
| 19 | Follows. Sawmill and ore pit guards are level 1 | Follows. Level is decision 4 |
| 20 | Partly. Area divisor 200, and level 1 near a start town | Follows |
| 21 | Does not. Guards are spaced as they are placed | Does not |
| 22 | Does not. One or two 3-tile entrances per border | Follows |
| 23 | Follows, but built before buildings | Follows |
| 24 | Follows, plus a border ridge term | Follows, no ridge term |
| 25, 26 | Follows | Follows |
| 27 | Follows, extended with forced seaports | Follows, extended |
| 28 | Does not | Check yes, repair no |
| 29 | Follows (`steps/gameplay/mines.py:655`) | Follows |
| 30 | Does not patch. Applied before the write | Does not patch |
| 31 | Partly. Two of four stores are versioned | Follows |
| 32 | Does not. No install flag exists | Does not |

### Lookups resolved

| # | Answer |
|---|---|
| L1 | All seven parts exist in some form. See the parts table |
| L2 | Buildings go after scenery (`cli.py:174`, `steps/gameplay/step.py` docstring) |
| L3 | Passage guards are posted per planned entrance. No dedupe exists. A spacing rule replaces it (`steps/placement.py:139`) |
| L4 | No repair exists. No map-level check runs |
| L5 | The scenario is written into the document before the file is written (`renderers/vmap.py:54`) |
| L6 | An underground level exists. It stays out of scope |
| L7 | Statistics live in `data/pp/`. Two of four stores carry a version |
| L8 | The catalogue lists random classes by level for monsters and dwellings, and random artifact classes by rank (`ontology.py:141-193`). Pools by purpose were not traced |

## 6. Slices

The generator already runs end to end, so each slice widens what the player can trust about
the map they get.

| # | Slice | Parts and concepts | Done when |
|---|---|---|---|
| 1 | The run proves every target is reachable | Passage: Reachability check. Delivery: Map file | `generate` checks the finished map, prints the verdict, and fails on any unreachable entrance or pickup. The seed sweep passes |
| 2 | The same seed gives the same file on any machine | Delivery: Map file | Two runs, one with a VCMI install and one without, give byte-identical files for the same request |
| 3 | Borders open like the corpus | Passage: Gate band, Keep-clear set. Scenery: Scenery process | Each border's open share lies within 0.39 to 0.54 over the sweep. Slice 1 still passes. One gate band concept remains |
| 4 | Each passage has one guard at the corpus-rule level | Loot and guards: Guard post, Guard strength | Each gate band holds at most one guard. Guard levels follow one rule table. Slice 1 still passes |
| 5 | Stale statistics never reach a map | Corpus statistics: Statistics store | Bumping any statistic's schema makes the next run re-mine it, for all four stores |
| 6 | The CLI tells the truth about start regions | Holdings: Start region | `--players` help describes the spread rule, and each start town sits in a distinct, spread region on the sweep |

Slice 3 waits on decision 3. Slice 4 waits on decision 4.

## 7. Open decisions

1. **Buildings before or after scenery?** Options: before, as the spec orders, with scenery
   pulled toward mines. After, as the code does, with buildings set against scenery and room
   reserved for start towns. Recommendation: after. Reason: the code and a settled decision
   already do it, and contact scoring gives the corpus overlap without an attraction term.
   If "after" stands, claim 17 is rejected, Placement field becomes a contact score, and
   Start region gains a room reserve.
2. **What guards reachability on the finished map?** Options: construction only, as the
   code does. Construction and a check. Construction, a check and a repair, as the spec
   says. Recommendation: construction and a check that fails the run. Reason: the spec says
   repair never fires, and a silent carve would hide a construction bug.
3. **Open borders or isolated regions?** Options: corpus-open gate bands, as the spec and
   invariant 12 say. One or two 3-tile entrances per border behind a scenery ridge and a
   border closure, as the code does. Recommendation: corpus-open bands. Reason: the section 1
   done-when asks for corpus openness, and isolation is what drives the border closure,
   portals and sealed regions. If isolation is the intent, the done-when line is wrong and
   changes instead.
4. **Which guard level numbers win?** Options: the code (sawmill and ore pit at level 1,
   passage divisor 200) or the spec (level 3, divisor 250). Recommendation: the code.
   Reason: a start hero must take its own wood and ore in the first week.
5. **Where does the file header come from?** Options: the first random-map file in the
   local install, else the template, as the code does. The template always.
   Recommendation: the template always. Reason: the install and the glob order change the
   bytes, and invariant 2 forbids that.
6. **Parked: the repo's structure beyond this problem.** Steps share one mutable workspace
   and a `run(ontology, map_state)` signature (`pipeline.py:102`, `:185`) instead of a
   typed product per part (F6). Corpus mining sits inside the steps that use it. The scenery
   step does work that belongs to three other parts. See `target-architecture`.
7. **Parked: extras outside this problem.** The underground, sealed regions with treasure,
   portals and seer-hut quests have no place in this note's scope. Recommendation: leave
   them until decision 3 settles, then revisit border closure and portals first.
