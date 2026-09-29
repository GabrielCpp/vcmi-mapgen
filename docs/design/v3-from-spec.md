# v3: the map generator, decomposed from its as-built spec

Input: `docs/specs/pp-map-generator-solution.md`, an as-built reference of an earlier
generator. This note treats it as a solution. Its facts and requirements become section 1.
Its design decisions become the claims in section 1b.

**Disclosure.** Before this skill loaded, my context already held descriptions of the
existing solution:

- The root `AGENTS.md`. It lists the current modules: a `generate` CLI, a step pipeline
  with a shared placement workspace, a map-state model, one subpackage per step, a gate
  statistics package, a zone plan that builds "zone entrances, the walkable web and the sea
  plan", a vegetation step, a terrain placement gate, and the ontology with its accessors.
- A memory note titled "Gameplay after vegetation". It records a settled design: all
  gameplay placed after vegetation, sprite top against trees, corpus-rate zone totals.
- The git log subjects, including "place every gameplay object after vegetation", "keep
  room for player towns" and "draw the gate count and spacing from the corpus".

The input spec also names its own modules (`macro_topo`, `pp_gameplay`, `pp_sample`,
`pp_pickup`, `pp_map`). I did not read any other file about the existing system before
section 5. To keep clear of those names, sections 2 to 4 say "region" where the spec says
"zone", "crossing" where it says "gate", "route network" where it says "web", "scenery"
where it says "vegetation", and "holding" for towns, mines, dwellings, visitables, banks
and shipyards. Each part and concept was checked against the test "would I have named this
without having seen the solution?". "Region" and "crossing" pass: H3 random map templates
use zones and connections, and a hand mapmaker speaks of regions and border crossings.
"Scenery" passes: the game calls these obstacles or decorations. One concept is at risk,
and it is flagged where it appears: "Reserved ground" is close to the spec's
"protected set".

## 1. Problem

**Who feels this.** A Heroes III player or mapmaker using VCMI wants a fresh map from one
number. Today they either draw a map by hand for hours or use a template generator whose
maps do not look or play like the hand-made maps in a 159-map corpus.

**What done looks like.** From one integer seed, a size and a player count, the person gets
a map that opens in the VCMI editor and plays:

- It opens in the editor with no warnings, and a PNG shows exactly what the editor shows.
- The same seed and options give the same file, byte for byte.
- Each of N players owns a start town at the centre of its region. On a 72 by 72 map with
  4 players, the starts land in four different quadrants, at least about 29 tiles apart.
- A hero can walk from any region to every town, mine, dwelling, visitable and pickup on
  the same landmass. On another island, a boat reaches it.
- The land splits into a handful of large regions whose sizes follow the corpus
  distribution. Seas are coherent bodies, or an archipelago on request.
- Scenery covers each region at the corpus rate, within a few points. Every border keeps
  at least the corpus open share of its length clear, 0.39 to 0.54 depending on terrain.
- Every mine has a guard that the hero must fight to flag it. Every map has all six basic
  mine types. Gold mines number at most one fewer than the towns.
- Every guard's strength follows what it guards.
- A 144 by 144 map holds about four times the content of a 72 by 72 map, not the same
  amount.
- Across seeds, rare visitables appear, and every object kind the corpus uses on land can
  appear.
- Water is part of the game: shipyards on coasts, boats, whirlpools and sea loot.

**Facts from the domain that the design leans on.**

- A map is a tile grid of terrains plus objects. An object has a footprint of blocking and
  visitable cells and is visited from a neighbouring tile. Water and rock are impassable.
- The editor's object table defines what an object is: its identity, footprint, allowed
  terrains and category. The corpus says how much and where, never what.
- The editor has random classes: random town, random dwelling by level, random resource,
  random artifact by tier and random monster by level. The game rolls the concrete object
  at start. They draw as labelled coloured discs, and those discs are the real sprites.
- A monster blocks its tile until a hero defeats it. A creature bank is its own fight.
- In the file, a town belongs to a player only when the town object names its owner. The
  header's main town alone leaves it neutral.
- Corpus measurements: regions are few and large. Two touching regions never share a
  terrain. Region borders are wide: 39 to 54 percent of a border's tiles stay open. The
  rate of guards is flat with distance to a border. Mines have a guard within 3 tiles in 64
  percent of cases, resource piles in 54 and reward pickups in 59. Scenery footprints
  stack. Scenery pairs attract at every range. Chests make up 9,071 of about 14,500 reward
  pickups. A region almost never holds three mines of one kind.

**Out of scope.**

- Underground levels and two-level play.
- Roads, rivers, placed heroes, quests and portal chains.
- Fair starts beyond dispersion, such as mirrored mines and dwellings between players.
- Scoring generated maps against corpus acceptance bands.
- Faction and level links on random dwellings.
- A fitted model of guard strength against guarded value.
- Reading the original `.h3m` files. The corpus arrives in a readable form.

## 1b. Claims

1. Plan macro structure first. Use the learned terrain Markov chain only for border texture,
   in a 2-tile band around region borders.
2. The water mask is low-frequency value noise thresholded at the water-fraction quantile.
   Islands use a noise wavelength half as long.
3. Zone target areas are drawn from the corpus distribution and rescaled to fill the land
   budget. Seeds are spread by minimum-distance rejection. Terrains are assigned by
   Metropolis on the seed k-NN graph with energy -log A[ti][tj].
4. Zones grow by capacity-constrained multi-source Dijkstra with jittered edge costs.
5. After tiling, zones are re-found by flood fill. Water and rock are segmentation
   barriers, never zones.
6. Placement intensities are counting fits: closed-form, Laplace-smoothed log relative
   intensity per covariate bin, clipped at plus or minus 2. No optimizer.
7. Anchors are drawn with `rng.choices(zone_tiles, weights, k=80)` and a 25-step spiral
   nudge. Sampling, not argmax.
8. Counts are stochastic rounding of density times area, under area-scaled soft caps.
9. Favour the editor's random classes at fixed shares per purpose.
10. Fixed identities are weighted by square-root damped corpus frequency with a 20 times
    penalty for repeats within a zone.
11. Creature banks are placed like visitables, with their own density, and no approach
    guard.
12. The mine economy: sawmill and ore pit first; a town zone has at least 2 mines anchored
    next to the town; further mines of distinct types; a map-level ledger in sorted zone
    order covers the six basics and rations gold to towns minus one.
13. Gameplay is placed before vegetation. Vegetation is attracted to mines by a +0.7
    log-intensity bonus in a 3-tile ring.
14. Gameplay footprints sit fully in the zone, at least `GAP=2` tiles from each other, off
    every reserved approach tile, with their own approach standable.
15. A mine guard stands on the mine's approach tile. The other four approach tiles are
    sealed with single-cell blocking decorations.
16. A gate guard stands at the band's narrowest tile with probability 0.65, level
    `min(7, 1 + area // 250)` plus a chance of one more. (The decision log says "band
    centres". Section 6.7 says the narrowest tile.)
17. Corridor dedupe: of two guards within 2 tiles, keep the stronger.
18. A shipyard appears with probability `min(0.8, density x area x 3)`. The x3 makes up
    for conditioning on coastal zones.
19. Gate bands: each contact front keeps a band of `max(3, open_frac x front_len)` tiles
    open, sized by the corpus border open fraction.
20. The protected web is a spanning tree of geodesic paths over farthest-point nodes, band
    representatives and every approach tile. It is built after gameplay and before
    vegetation, and it is a hard zero for vegetation.
21. Vegetation is a Gibbs marked point process on object configurations, fitted per
    terrain, sampled by birth and death Metropolis-Hastings at 40 proposals per tile.
22. Two scales: a log-Gaussian Cox field for forest masses and clearings, and a
    Geyer-saturated pair potential for local structure.
23. No vegetation hard core. Stacking is priced. Coverage is steered to the corpus by a
    global offset.
24. Pickups run over the finished open field, after vegetation.
25. Guarded caches sit in pockets whose mouth has clearance at most 2 and web distance at
    least 3. The guard stands on the mouth. Its level follows the cache value.
26. Unguarded scatter is loot: random artifacts drop to a 15 percent share.
27. Roaming guards stay off the web, at least 7 tiles apart, levels 1 to 4.
28. Water is mined and populated as raw connected components.
29. Guard levels are heuristic bands per guard kind.
30. The G2 gate verifies reachability over the whole map and repairs by carving through
    vegetation only, up to 6 rounds. Off-island targets do not fail it.
31. Player zones are chosen by greedy max-min centroid distance.
32. A forced start town is anchored at the zone centroid by an exhaustive nearest-first
    scan.
33. Playability is a post-export patch on the `.vmap`, not part of the writer.
34. Corpus statistics are cached in versioned data files. A version mismatch re-mines.
35. Every RNG is `Random(seed ^ id * large-odd ^ salt)` with a salt per module.
36. A batch cycles the water mode: normal, islands, none.
37. The `.vmap` header comes from a real VCMI random map.
38. Each land zone runs gameplay, web, vegetation and pickups in turn.

## 2. Parts and concepts

### Level 1: parts

1. **Corpus learning.** Owns what real maps look like, as measured numbers: region sizes,
   terrain mixes, object rates, where objects tend to stand, how scenery clusters, how
   open borders are, how often things are guarded. Never knows a seed or a generated map,
   and never decides what an object is. Hands a statistics book to every generating part.
2. **Landscape.** Owns the shape of land and water: how much sea and where, how many
   regions, their sizes and terrains, the look of their borders and each tile's
   appearance. Never knows any object. Hands a region map to all later parts.
3. **Holdings.** Owns the fixed sites a hero visits: towns, mines, dwellings, visitables,
   creature banks and shipyards. It decides how many each region holds, which kind, where
   each stands, and where the players start. Never knows how scenery was drawn, only the
   open ground it left, and never knows guards or loot. It picks the start regions and
   their town room before scenery grows, and places every site after. Hands start room to
   Passages, and placed sites with their approach tiles to Passages and Guards and treasure.
4. **Passages.** Owns the promise that a hero can walk everywhere and only where the map
   allows: the open border crossings, the closed rest of each border, the route network
   inside each region, and the final verdict on the finished map. Never knows what kind of object waits at an approach, only where the approach is.
   Hands reserved ground to Scenery, routes and crossings to Guards and treasure, and the
   verdict to Scenario file.
5. **Scenery.** Owns trees, mountains, rocks and the rest of the dressing, placed to match
   the corpus look. Never knows what a holding is, only which tiles are reserved. Hands the
   finished open ground to Holdings, Guards and treasure, and Passages.
6. **Guards and treasure.** Owns monsters and loot: guards on mines and crossings, guarded
   caches in dead ends, loose loot along routes, roaming monsters and sea contents. Never
   knows how scenery was drawn, only the open ground it left. Hands guards and pickups to
   Passages for the verdict and to Scenario file.
7. **Scenario file.** Owns what the person receives: the editor file with its players,
   teams, owners and victory rules, the picture, and an optional install. Never knows how
   anything was chosen.

Two things every part consults, owned by none of the seven:

- **Object catalog**, a read-only reference: the editor's object table. Identity,
  footprint, allowed terrains and category. Every part that names an object asks it.
- **Draw stream**, a shared value type: a random source derived from the seed and a
  stable key such as a region or a water body. It is the only source of chance.

**Flow.**

```
corpus maps ──▶ Corpus learning ──▶ statistics book (kept between runs)
seed, size, players, teams, water mode
  ──▶ Landscape ──region map──▶ Holdings (start choice) ──start room──▶ Passages (build)
  ──reserved ground──▶ Scenery ──open ground──▶ Passages (close borders)
  ──▶ Holdings (sites) ──sites + approaches──▶ Guards and treasure
  ──guards + pickups──▶ Passages (verdict) ──▶ Scenario file ──▶ .vmap + PNG
```

Each part runs over every region before the next part starts. Crossings and the mine
ledger span two or more regions, so no region runs ahead of the others. Holdings and
Passages each run at two moments. The start choice must reserve its room before scenery
can fill it, and the border can close only once scenery has drawn its side.

**Tests of the split.**

- In one paragraph: we study real maps to learn how they look. We draw the land and the
  sea and split the land into regions. We put towns, mines and other buildings in each
  region, and pick where the players start. We keep border crossings and roads open so
  every building can be reached. We dress the rest with forests and mountains the way real
  maps do. We add monsters and treasure. We write the file the game opens, with the
  players and teams.
- Two code bases fit it: a step pipeline over one mutable map, or pure functions that each
  return a new layer.
- No part carries a stage or module name I have seen. "Passages" is not "gate" or "web".
  "Scenery" is not "vegetation". "Holdings" is not "gameplay" or "placement".

### Level 2: concepts

**Corpus learning** (6 concepts)

| Concept | Owns | Never knows |
|---|---|---|
| Corpus map | One real map read as regions, tiles and catalog-resolved objects | How any statistic is used |
| Geography profile | Region-size distribution, terrain shares, terrain adjacency, water fraction | Objects |
| Rate | A count over its exposure: objects per tile, open share of a border, guarded share of a purpose, objects per coastal tile | Where objects stand |
| Tendency estimate | Relative intensity of a purpose per covariate bin (rim distance, border distance, openness) | How a sampler draws from it |
| Clustering estimate | Scenery pair correlation, category and sprite mix, coverage, coarse overdispersion | The sampler |
| Statistics book | The stored results, keyed by schema version | How any number was computed |

The Statistics book is a read-only reference for every generating part.

**Landscape** (7 concepts)

| Concept | Owns | Never knows |
|---|---|---|
| Sea plan | How much water and its shape, per water mode | Regions |
| Region plan | Number of land regions, their target areas, seed points and terrains | Tiles |
| Region growth | Assigning tiles to regions until each reaches its target, with organic borders | Terrain texture |
| Border texture | Corpus-like terrain mixing in a narrow band along borders | Region interiors |
| Tile appearance | The transition view each tile shows, from its neighbours | Regions |
| Region reading | Finding regions as a player sees them from the finished tiles. Water and rock are barriers | How the plan was made |
| Region map | The finished regions, terrains, border fronts and water bodies | Objects |

Region map is a shared value type every later part reads.

**Holdings** (7 concepts)

| Concept | Owns | Never knows |
|---|---|---|
| Quota | How many of each purpose a region gets | Where they go |
| Start choice | Which regions host player starts, spread apart | Object kinds |
| Candidate walk | The order in which a site's anchor tiles are tried | Why a tile fits |
| Site rule | Whether one footprint may stand on one tile | The order of tries |
| Kind choice | Which exact object fills a purpose, random class or fixed | Where it stands |
| Mine ledger | Which mine types the map still needs and which it has used | Tiles |
| Landing | The one shipyard each shore needs so a boat can leave that landmass | Inland sites |

Placed object (identity, anchor, purpose, approach) is a shared value type.

**Passages** (5 concepts)

| Concept | Owns | Never knows |
|---|---|---|
| Crossing | The open stretch of one border between two regions, and its narrowest tile | Routes inside a region |
| Route network | Paths linking every crossing, spread points and approach tile of a region | Scenery |
| Reserved ground | The union of tiles scenery may never block | Why each tile is reserved |
| Border closure | Closing every border tile outside the crossings, so regions meet only there | How the crossings were sized |
| Reachability verdict | Whether every target is reachable, with guards passable and other islands boat-reachable | How the map was built |

Reserved ground is a value type Passages hands to Scenery. It is the concept nearest to a
name I saw in the spec, "protected set". I would have named it without the spec, because
the problem demands a set of tiles that scenery may not touch.

**Scenery** (6 concepts)

| Concept | Owns | Never knows |
|---|---|---|
| Base rate | Scenery per category by rim distance | Pair interactions |
| Mass field | Large-scale density variation: forest masses and clearings | Local pairs |
| Local interaction | Saturated pair potentials between nearby scenery | Large-scale variation |
| Coverage steer | The global offset that reaches the corpus coverage | Single proposals |
| Scenery sampler | The chain that adds and removes scenery under the hard zeros | How statistics were estimated |
| Sprite choice | Which sprite within a category, by corpus mix | Position |

**Guards and treasure** (7 concepts)

| Concept | Owns | Never knows |
|---|---|---|
| Guard strength | A guard's level from the value it guards, per guard kind | Where guards stand |
| Mine guard | The guard on a mine's approach and the seals on its other sides | Strength rules |
| Crossing guard | Whether a crossing is guarded, once per crossing, at its narrowest tile | Region interiors |
| Pocket | A dead end in the open ground with a narrow mouth, and the cache inside | Loose loot |
| Loose loot | Unguarded pickups along routes, by corpus mix | Pockets |
| Roamer | Roaming monsters away from routes | Pickups |
| Sea contents | What each water body holds | Land |

**Scenario file** (6 concepts)

| Concept | Owns | Never knows |
|---|---|---|
| Player slots | N playable slots, their teams and their main towns | Objects other than towns |
| Ownership | The owner written on each start town object | Slots beyond their colour |
| Victory rules | Defeat all enemies, and the standard defeat | Players |
| Editor file | The `.vmap` archive: header, terrain, objects with identity and visit sides | How players were set |
| Picture | The PNG in the editor's drawing order | The file |
| Install | Copying files into a dedicated editor folder, on request | Content |

No part has more than 7 concepts. No concept needs "and" except Mine guard (a guard and its
seals) and Pocket (a dead end and its cache). Both stay whole: the seals exist only for the
guard, and the cache exists only for the pocket.

## 3. Invariants

1. **Same seed, same options, same bytes.** Owner: Draw stream. Every part derives its
   randomness from it and sorts before each weighted draw. A breach shows as two runs that
   differ, so the check is a two-run comparison.
2. **Every site approach and pickup is reachable over land from its landmass, with guards
   passable. A target on another landmass counts as boat-reachable when its own landmass
   and the start's both have a shipyard.** Owner: Reachability verdict. Upheld by Crossing,
   Route network, Site rule, Scenery sampler, Border closure, Mine guard and Landing.
3. **No blocking scenery cell lies on reserved ground: crossings, routes and the start
   towns' room.** Owner: Scenery sampler. It rejects the proposal.
4. **Identity, footprint, terrain coupling and category come from the object catalog, never
   from the corpus.** Owner: Object catalog. An unknown object fails the lookup. Upheld by
   Corpus map, Kind choice and Sprite choice.
5. **A holding's footprint lies inside its region on allowed terrain, at least 2 tiles
   from any other holding, off every other holding's approach, with its own approach
   standable, and it never cuts reachable ground in two.** Owner: Site rule.
6. **Every mine is guarded on its approach and cannot be visited from any other side.**
   Owner: Mine guard.
7. **The map holds all six basic mine types whenever it holds at least six mines. Gold
   mines number at most towns minus one. No region holds two mines of one kind. A region
   with a town holds a sawmill and an ore pit next to it.** Owner: Mine ledger.
8. **Each start region holds a start town whose centre is within 1.5 tiles of the region
   centre.** Owner: Start choice. Upheld by Candidate walk and Site rule.
9. **Each start town object names its player as owner, and exactly N slots are playable.**
   Owner: Player slots. Upheld by Ownership.
10. **Water and rock never form a region, and two touching regions never share a
    terrain.** Owner: Region reading. Upheld by Region plan.
11. **Every crossing keeps at least the corpus open share of its border, and never fewer
    than 3 tiles, clear.** Owner: Crossing.
12. **Every guard's level is a function of what it guards.** Owner: Guard strength.
13. **Region sizes follow the corpus distribution.** Owner: Region plan.
14. **Two regions meet on walkable ground only at a crossing.** Owner: Border closure.
    Upheld by Crossing.

## 4. Forces and patterns

### Forces

1. **Determinism.** One seed must give one file, and a region's draws must not depend on
   the order other regions ran.
2. **The corpus is slow to read and rarely changes.** 159 maps.
3. **The statistics schema grows.** It changed five times in the spec's history.
4. **Purposes grow.** Banks joined late. Each purpose carries a density, a cap base and a
   random-class share.
5. **Tests must run without the corpus or the game's sprite files.** CI has neither.
6. **Later parts read earlier parts' output.** Holdings need regions and the open ground
   scenery left. Scenery needs reserved ground. Treasure needs the open ground scenery and
   holdings left.
7. **Two parts span regions.** Crossings belong to two regions. The mine ledger spans the
   map.
8. **One hard guarantee, two breakers.** Reachability is the only hard guarantee.
   Scenery is dense enough to break it, and a holding placed into scenery can close the
   last gap.
9. **The scenery look is a combination of independent effects.** Rim distance, mass
   field, local pairs and coverage offset.
10. **Map size varies 4 times in each direction.** Counts must scale with area.
11. **Rare kinds must appear.** Raw frequency weighting starved them.
12. **Guard strength depends on the guard's kind.** Mine rarity, region size, cache value,
    a fixed band for roamers and sea monsters.
13. **Water mode varies per run.** None, normal, islands.
14. **Two outputs read one finished map.** The file and the picture.
15. **Start placement must not fail when the footprint fits anywhere.**
16. **Hand-made maps set buildings with their backs against scenery.** A site placed on
    bare ground and dressed afterwards does not look like the corpus.

### Between parts

- **A sequence of stages handing one growing map value**, for force 6. Each part reads what
  earlier parts added and adds its own layer. Stages run part-major, every region before
  the next part, for force 7.
- **Read-only references passed in at the root**: the Statistics book and the Object
  catalog, for force 5. A test passes a small book and catalog. No part loads them itself.
- **Construct, then verify**, for force 8. Passages builds reserved ground before Scenery.
  Site rule refuses any holding that would cut reachable ground. The Reachability verdict
  checks the finished map. The verdict is an oracle: measure,
  targets, verdict. Its tolerance is zero.

### Inside each part

- **Corpus learning.** Statistics book: a cache keyed by schema version, stored as data,
  for forces 2 and 3. Rate and Tendency estimate: plain functions with closed-form
  estimators, for force 1. The per-purpose parameters live in one data table keyed by
  purpose, for force 4.
- **Landscape.** Sea plan: a function with the water mode as a parameter, for force 13.
  The rest are plain functions in sequence.
- **Holdings.** Candidate walk: one function whose ordering is a parameter, weighted random
  for ordinary sites and nearest to centre for start towns, for forces 11 and 15. It tries
  every candidate before giving up. Site rule: one function with early returns. The rules
  do not vary, so a chain of predicates would be decoration. Mine ledger: a value threaded
  through regions in sorted order, for forces 1 and 7. Quota and Kind choice: plain
  functions over the purpose table. Candidate walk, for force 16, prefers among nearby
  legal anchors the one whose back rests against scenery. Landing: a plain function per
  shore, for force 8. When Candidate walk finds no site for a drawn object, Kind choice
  draws again under a smaller footprint ceiling. This is a retry in the flow, not a
  concept.
- **Passages.** Crossing: computed once per border between two regions, for force 7.
  Reserved ground: a value type. Border closure: a plain function over each border after
  scenery. Reachability verdict: an oracle, for force 8.
- **Scenery.** The conditional intensity is a weighted sum of term functions in log space,
  for force 9. The sampler is one plain loop.
- **Guards and treasure.** Guard strength: a dict from guard kind to a level function, for
  force 12. No strategy protocol, because the kinds are fixed today.
- **Scenario file.** Editor file and Picture: two readers of the same finished map value,
  for force 14. The picture reads sprites through a port with an adapter for the local
  game files and a test adapter, for force 5. Player slots, Ownership and Victory rules
  are fields the Editor file writes, not a patch applied after writing.

### Claims

| # | Verdict | Force or reason |
|---|---|---|
| 1 | Kept | Corpus regions are large, and the chain fragments them. Texture is wanted only at borders. |
| 2 | Kept | Force 13. Coherent seas are a requirement. |
| 3 | Kept | Invariants 10 and 13. Any sampler that respects terrain adjacency and forbids same-terrain contact would do. Metropolis is one. |
| 4 | Kept | Exact target areas with organic borders. |
| 5 | Kept | Invariant 10. Regions must be the ones a player sees. |
| 6 | Kept | Force 1 and small per-terrain counts. |
| 7 | Rejected | Sampling over argmax is kept for variety. The fixed budget of 80 and the spiral nudge have no force, and the forced-town failure shows the budget fails. Replaced by Candidate walk, which tries every candidate. |
| 8 | Kept | Force 10. Rounding by chance keeps the corpus mean while varying per region. |
| 9 | Kept | A user requirement and H3 convention. Levelled random monsters make force 12 possible. |
| 10 | Kept | Force 11. |
| 11 | Kept | Domain fact: a bank is its own fight. |
| 12 | Kept | Invariant 7 and forces 1 and 7. |
| 13 | Rejected | Force 16: holdings go after scenery, backed against it. Force 8 holds through reserved start room and a Site rule that refuses any cut. The +0.7 pull has nothing to act on once mines come after scenery. |
| 14 | Kept | Corpus fact: buildings do not stand wall to wall. |
| 15 | Kept | Invariant 6 and a user playtest. |
| 16 | Kept, narrowest tile | Corpus guard rate is flat by border distance, so a rule is right. The spec contradicts itself. The narrowest tile is the chokepoint a single monster can hold. |
| 17 | Rejected | Duplicates come from each region guarding its own side. A crossing owned once per border places one guard by construction. |
| 18 | Rejected | The x3 corrects a rate measured over the wrong exposure. Landing guarantees one shipyard per shore, for force 8. Any extra shipyard comes from Rate, measured per coastal tile. |
| 19 | Kept | Corpus fact: borders are 39 to 54 percent open. |
| 20 | Kept | Force 8. |
| 21 | Kept | Requirement: the corpus look. |
| 22 | Kept | Corpus fact: pairs attract at every range, and a purely attractive process explodes. |
| 23 | Kept | Corpus fact: scenery footprints stack. |
| 24 | Kept | Force 6: pockets and openness exist only once scenery is down. |
| 25 | Kept | Requirement: caches sit in real dead ends, behind a fight. |
| 26 | Kept | Corpus fact: chests dominate reward pickups. |
| 27 | Kept | No force for keeping roamers off routes beyond style. Kept as a data parameter. |
| 28 | Kept | Invariant 10: water is never a region. |
| 29 | Kept | A fitted model is out of scope. |
| 30 | Split | The verdict is kept, for force 8. Repair is rejected: the spec reports it never fires, and a repair that hides a broken construction hides a bug. See section 7. |
| 31 | Kept | Requirement: spread starts. |
| 32 | Folded into Candidate walk | Same force as claim 7, force 15. |
| 33 | Rejected | Its force is a writer shared with another pipeline. Nothing in this problem shares the writer. See lookup 1. |
| 34 | Kept | Forces 2 and 3. |
| 35 | Kept | Force 1. |
| 36 | Kept | Requirement: a batch shows the three map archetypes. |
| 37 | Kept | Domain fact: the editor needs a valid header. |
| 38 | Rejected | Force 7: crossings and the ledger span regions. Part-major order replaces region-major. |

### Open lookups

1. Does the existing `.vmap` writer have callers other than the generator? Decides claim
   33.
2. Is there a versioned statistics cache, and in what shape? Decides the Statistics book.
3. In which order does the existing system place holdings and scenery? Decides claim 13.
4. Does the reachability repair ever fire across a seed sweep? Needs a run. Decides claim
   30.
5. Does the corpus give a measurable pull between mines and scenery? Needs a measurement.
   Decides the weight in claim 13.
6. Does the object catalog expose each object's visit sides and a pool of single-tile
   blocking scenery per terrain? Decides Mine guard.
7. Does the existing system already reach underground? Decides whether the scope line
   holds.

## 5. Mapping onto the existing system

### Revision log

1. Section 2, Holdings: now runs at two moments. Start choice reserves town room before
   scenery, and every site is placed after scenery. Finding: the code places every
   holding into the finished scenery (`vcmi_mapgen/cli.py:187-195`,
   `steps/gameplay/site.py:1-11`) and reserves town room first
   (`steps/zone_plan.py:241-317`).
2. Section 2, Holdings: added Landing. Finding: the code guarantees one shipyard per shore
   (`steps/zone_plan.py:117`, `steps/gameplay/shipyards.py:109`). Boat reachability in
   invariant 2 depends on it.
3. Section 2, Passages: added Border closure. Finding: the code closes every border tile
   outside the planned crossings (`steps/vegetation/border_plan.py:152`,
   `steps/border/step.py:1`). A crossing guard holds nothing if the border is open
   elsewhere.
4. Section 2, Passages: removed Repair. Finding: section 4 already rejected repair under
   claim 30, and the code has none. The concept contradicted its own section.
5. Section 2, Scenery: dropped "which tiles attract". Finding: the code's sampler has no
   pull toward mines, and mines now come after scenery.
6. Section 3: invariants 2, 3 and 5 reworded, invariant 14 added, for revisions 1 to 3.
7. Section 4: forces 6, 8 and 9 reworded and force 16 added, for revision 1. Claims 13
   and 18 changed verdict. Candidate walk prefers backed anchors
   (`steps/gameplay/site.py:70`, `:397`). Holdings flow retries with a smaller footprint
   (`steps/gameplay/step.py:108`).

### Open lookups, resolved

1. The `.vmap` writer has one caller, the CLI (`cli.py:256`). Slots, owners and victory
   are applied inside `VmapRenderer.render` before the write
   (`renderers/vmap.py:53-55`). Claim 33 stays rejected, and the code already agrees.
2. The code keeps several versioned caches, one per statistics family:
   `STATS_VERSION = 5` (`steps/gameplay/mines.py:38`), `GATE_STATS_VERSION = 2`
   (`steps/gate/gates.py:21`), and files under `data/pp/`. Statistics book: Reshape.
3. Scenery runs first and holdings after (`cli.py:187-195`). Claim 13 changed.
4. The code has no repair. It fails loudly on a walled-off pocket
   (`steps/vegetation/step.py:49`). No sweep was run. The question is moot.
5. Not measured. The reversal of claim 13 leaves the pull nothing to act on.
6. Yes. The catalog serves single-tile blocking scenery per terrain
   (`ontology.decor_pool(..., blocking=True, max_cells=1)`, used at
   `steps/gameplay/site.py:466`). The writer derives visit sides from each mask
   (`renderers/vmap.py:57-62`).
7. Yes. `--subterrain` adds a second level with tunnels and gate pairs
   (`cli.py:182`, `steps/terrain_gen/step.py:116`, `steps/gameplay/gate_pairs.py`). The
   scope line holds for this note. Section 7 decision 2 asks whether it should.

### Parts

| Part | Verdict | Where, and the mismatch |
|---|---|---|
| Corpus learning | Reshape | No part exists. Mining lives inside its consumers: `steps/terrain_gen/macro_topo.py:132`, `steps/vegetation/stats.py`, `steps/gameplay/mines.py:38`, `steps/gate/gates.py:21`. `mines.py` also holds the player-zone pick (`:655`). The design is right: a generating step should never know how a number was measured. |
| Landscape | Exists | `steps/terrain_gen/macro_topo.py` (water mask `:179`, areas `:307`, Metropolis `:343`, growth `:389`, border band `:54`), `markov.py`, `steps/segment/step.py`. Owns and never-knows match. |
| Holdings | Exists | `steps/gameplay/`: `step.py`, `site.py`, `draw.py`, `shipyards.py`. Two concepts sit elsewhere, listed below. |
| Passages | Reshape | Spread over five homes. Crossings in `steps/zone_plan.py:213`, the route network in Scenery's module (`steps/vegetation/sample.py:195`), reserved ground as mutable fields on a shared workspace (`pipeline.py`), border closure in two steps, and the only verdict after scenery (`steps/vegetation/step.py:33`). The design is right: invariants 2 and 14 need one owner each. |
| Scenery | Exists | `steps/vegetation/sample.py` (`_ZoneSampler` `:326`, 40 proposals per tile `:62`, saturation `:63`, Cox cell `:64`, coverage steer `:558`). One mismatch: a border bias (`:269`) gives scenery a job that belongs to Border closure. |
| Guards and treasure | Reshape | Mine guard in `steps/gameplay/site.py:459`, crossing guards in `steps/border/entrances.py:80`, pockets in `steps/loot/caches.py`, loose loot in `steps/scatter/`, sea contents in `steps/zone_plan.py:172` and `steps/gameplay/water.py`. Guard strength is split across `mines.py:170`, an area rule in `entrances.py` and `gate_pairs.py:25`. No roamers exist. |
| Scenario file | Exists | `renderers/vmap.py:42-55` and `:167`, `kit/vmap/writer.py:102`, `renderers/png.py`. Install is absent. |

### Concepts

**Corpus learning.** Corpus map: Exists (`kit/objects.py`, `readers/vmap_reader.py`).
Geography profile: Exists inside Landscape (`macro_topo.py:132`), Reshape to move it.
Rate: Exists as densities per terrain (`steps/gameplay/draw.py:67`). The shipyard rate
uses the wrong exposure (claim 18). Tendency estimate: Exists (`mines.py:495-524`).
Clustering estimate: Exists (`steps/vegetation/stats.py`). Statistics book: Reshape,
several caches owned by their consumers.

**Landscape.** Sea plan, Region plan, Region growth, Border texture, Region reading:
Exist in `macro_topo.py` and `steps/segment/step.py`. Tile appearance: Exists
(`kit/tiling.py`). Region map: Exists as `MapState.zones`.

**Holdings.** Quota: Exists (`draw.py:84`, `:108`). The code draws one total and splits
it by weight. The area-scaled soft caps of claim 8 are absent. Start choice: Reshape. It
lives in the statistics module (`mines.py:655`) and in the zone plan
(`zone_plan.py:278`). Candidate walk: Exists (`site.py:362-403`). Site rule: Exists
(`site.py:290`, `:335`, `:405`). Kind choice: Exists (`draw.py:122-137`). Mine ledger:
Exists (`steps/gameplay/step.py:224`). Landing: Exists (`zone_plan.py:117`,
`shipyards.py:109`).

**Passages.** Crossing: Exists (`zone_plan.py:213`). Route network: Reshape. It is built
in the scenery module (`sample.py:195`) and re-linked by Site rule's module
(`site.py:162`, `:436`). Reserved ground: Reshape. It is a set of mutable fields on the
shared workspace, not a value handed along. Border closure: Reshape. It has three homes:
the scenery rim bias (`sample.py:269`), the seal after scenery
(`steps/vegetation/step.py:166`, `border_plan.py:152`) and a later step
(`steps/border/step.py`, `border_seal.py`). Reachability verdict: Reshape. The live check
sees only walled-off pockets after scenery (`steps/vegetation/step.py:33-51`), before any
holding or guard exists. `kit/reachability.py` walks the finished map but has no caller
outside tests.

**Scenery.** Base rate, Mass field, Local interaction, Coverage steer, Scenery sampler,
Sprite choice: all Exist inside one class (`sample.py:326`). The split is internal, which
suffices.

**Guards and treasure.** Guard strength: Reshape, split in three. Mine guard: Reshape. It
lives in Holdings' site module (`site.py:459-494`). Site rule reserves its tile
(`site.py:304`), so moving it out cannot fail. Crossing guard: Exists, one per crossing
by construction (`entrances.py:80-91`). Pocket: Exists (`steps/loot/caches.py`). Loose
loot: Exists (`steps/scatter/scatter.py:21`). Roamer: New, in a new
`steps/roamers/` subpackage. Sea contents: Exists.

**Scenario file.** Player slots, Ownership, Victory rules: Exist (`renderers/vmap.py:167`).
Editor file: Exists (`kit/vmap/writer.py:102`). Picture: Exists (`renderers/png.py`,
`sprites.py`). Its sprite source has no test adapter: tests skip when the game files are
absent. Install: New, as a CLI flag.

### What the existing system has that the design lacks

- Border closure: a missed concept. Added (revision 3).
- Landing: a missed concept. Added (revision 2).
- Start-town room reserved before scenery: missed timing. Folded into Start choice
  (revision 1).
- Smaller-object retry (`steps/gameplay/step.py:108`): missed behaviour. Added to the
  Holdings pattern (revision 7).
- Player-town relocation (`steps/gameplay/step.py:269`): waste under the design. Reserved
  room and an exhaustive Candidate walk leave nothing to relocate. A seed sweep should
  confirm it never fires before it goes.
- `kit/reachability.py`: waste today, with no caller. It is the natural home of the
  Reachability verdict.
- The underground level and its gate pairs, gated regions (`steps/gated/`), treasure
  regions (`steps/treasure/`), portals (`steps/portal/`) and seer-hut quests
  (`steps/loot/`): outside section 1. Neither waste nor missed until the scope is
  decided. Section 7 decision 2.
- A shared mutable workspace that four steps edit in place (`pipeline.py`,
  `PlacementWorkspace` and `ProviderRegistry`). The design hands values from part to part.
  This is repo-wide. Parked in section 7.

### Claims against the code

| # | Code follows | Design follows |
|---|---|---|
| 1 | Yes (`macro_topo.py:3-19`, `:54`) | Yes |
| 2 | Yes (`macro_topo.py:179`) | Yes |
| 3 | Yes (`macro_topo.py:343`) | Yes |
| 4 | Yes (`macro_topo.py:389`) | Yes |
| 5 | Yes (`steps/segment/step.py`) | Yes |
| 6 | Yes (`mines.py:495-509`) | Yes |
| 7 | No. The walk tries every legal anchor (`site.py:380-403`) | No |
| 8 | Partly. Stochastic rounding without soft caps (`draw.py:84`) | Yes |
| 9 | Yes (`draw.py:140`) | Yes |
| 10 | Yes. Square root plus 0.3, repeats times 0.05 (`draw.py:131-133`) | Yes |
| 11 | Yes (`draw.py:207`) | Yes |
| 12 | Yes (`step.py:224`, `draw.py:94`) | Yes |
| 13 | No. Scenery first (`cli.py:187-195`) | No, after revision 1 |
| 14 | Yes (`site.py:295`) | Yes |
| 15 | Yes (`site.py:459-494`) | Yes |
| 16 | No. Probability 0.85 at the band's representative tile (`entrances.py:14`, `:86`) | Narrowest tile, rate open (section 7) |
| 17 | No dedupe. One guard per crossing and a spacing rule (`entrances.py:86`, `placement.py:139`) | No |
| 18 | No. One guaranteed shipyard per shore (`shipyards.py:109`) | No |
| 19 | Yes (`zone_plan.py:213`) | Yes |
| 20 | Partly. The web is built before scenery and extended to each approach after (`sample.py:195`, `site.py:436`) | Yes, same shape |
| 21 | Yes (`sample.py:62`) | Yes |
| 22 | Yes (`sample.py:63-64`) | Yes |
| 23 | Partly. Stacking is capped at 2 (`sample.py:65`) | Yes |
| 24 | Yes (`cli.py:200-201`) | Yes |
| 25 | Yes (`steps/loot/caches.py`) | Yes |
| 26 | Yes (`scatter.py:21`) | Yes |
| 27 | No. No roamers exist | Yes |
| 28 | Yes (`zone_plan.py:172-177`) | Yes |
| 29 | Yes, in three places | Yes, in one table |
| 30 | Verdict partly, repair no (`steps/vegetation/step.py:49`) | Verdict yes, repair no |
| 31 | Yes (`mines.py:655-680`) | Yes |
| 32 | Yes, through the general walk (`site.py:372`) | Yes |
| 33 | No. Playability is applied before the write (`renderers/vmap.py:53-55`) | No |
| 34 | Yes, as several caches | Yes, as one book |
| 35 | Yes (`site.py:269`) | Yes |
| 36 | No. One mode per run, default normal (`cli.py:206`) | Yes |
| 37 | Yes (`data/vmap_header_template.json`) | Yes |
| 38 | No. Step-major over all zones (`cli.py:181-201`) | No |

## 6. Slices

Most of the design exists. The slices order the reshape and the new work. Each ends in a
map someone can open.

1. **One reachability verdict over the finished map.** Parts: Passages. Concepts:
   Reachability verdict, reading guards as passable and Landing for boats. The verdict
   runs after the last object and fails loudly. Done when seeds 1 to 50 at sizes 72 and 144
   pass, and a map with one planted wall fails with the wall's position.
2. **Border closure in one place.** Parts: Passages, Scenery. Concepts: Border closure,
   Crossing, Scenery sampler. The rim bias leaves the sampler. Done when invariant 14 holds
   on the same sweep and scenery coverage stays within a few points of the corpus.
3. **One guard-strength table and a measured crossing rate.** Parts: Guards and treasure,
   Corpus learning. Concepts: Guard strength, Crossing guard, Mine guard, Rate. Done when
   every guard's level comes from the table, and the guarded share of crossings falls
   within the corpus band.
4. **Corpus learning as its own part.** Parts: Corpus learning, then every reader.
   Concepts: Statistics book, Geography profile, Rate, Start choice. The player pick
   leaves the statistics module. Done when a seed generates with a small test book and no
   corpus on disk, byte for byte the same as before for the real book.
5. **Roamers.** Parts: Guards and treasure. Concepts: Roamer, Guard strength. Done when a
   144 by 144 map shows roamers off routes at the corpus rate, and the verdict still
   passes.
6. **Install and a sprite test adapter.** Parts: Scenario file. Concepts: Install,
   Picture. Done when `--install` copies the map into a dedicated editor folder, and the
   picture tests run in CI without game files.

## 7. Open decisions

1. **Do holdings go after scenery?** Options: after scenery with the start room reserved
   first, as the code does and the revised design says; or before scenery, as the spec
   says. Recommendation: after scenery. Reason: buildings backed against scenery match the
   corpus, and Site rule already refuses any placement that cuts a path.
2. **What is in scope beyond section 1?** The code carries an underground level, gated
   regions, treasure regions, portals and seer-hut quests that the spec leaves out.
   Options: widen this note to cover them; keep them outside this note and decompose them
   in a follow-up; remove them. Recommendation: a follow-up note. Reason: each is
   part-sized, and portals would add a reachability path that Passages must own.
3. **Where does the reachability guarantee live?** Options: one verdict over the finished
   map that fails loudly; the current check after scenery alone; a verdict with repair.
   Recommendation: one verdict over the finished map. Reason: holdings and guards placed
   after scenery can also cut a path, and the current check never sees them.
4. **Which rate guards a crossing?** Options: the code's 0.85 at the representative tile;
   the spec's 0.65 at the narrowest tile; a rate measured from the corpus. Recommendation:
   measure it, and stand the guard on the narrowest tile. Reason: neither number has a
   source, and the narrowest tile is the one a single monster holds.
5. **Should a batch cycle the water mode?** Options: cycle normal, islands and none per
   seed; keep one mode per run. Recommendation: keep one mode per run until someone runs
   batches. Reason: no batch command exists, and the flag already reaches all three modes.
6. **Parked: the shared mutable workspace.** Four steps edit one `PlacementWorkspace` in
   place through the `ProviderRegistry`. The design hands one value from part to part.
   The fix spans every step, so it belongs to `target-architecture`, not this note.
   Recommendation: run `target-architecture` before slice 4. Reason: slice 4 moves
   Corpus learning across every step and would otherwise land on the workspace twice.
