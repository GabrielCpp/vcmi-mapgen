# Landmarks: every spot worth the walk

Disclosure: before this note was started I had read the vegetation grower and its sampler,
the gameplay drawer and step, the zone site, the catalog port and its VCMI adapter, and the
mod object reader. Three settled designs from memory also loaded: gameplay after
vegetation, effort reward, and decompose before coding. Their decisions are claims in 1b.

## 1. Problem

**Who feels it.** A player crossing a big place finds a small patch of another terrain, a
lava pool in rough ground or a meadow in dirt, and the patch is bare: no trees, no rocks, no
building. It reads as a hole in the map rather than a spot worth the walk. The same player
walks into a cove closed by mountains and pines, of the same snow as the zone around it,
and finds it empty too (seed 4 at size 72, the cove above the town near (26,6)).

**Done looks like.**

- Every spot holds something worth the walk. A spot is a patch of another terrain, or a run
  of reachable free land farther from every object worth the walk than the remote distance
  (A7). No rule limits a spot's size or its terrain.
- Each spot's landmark is the largest one that fits, drawn from the kinds spots hold on the
  corpus: a gold mine, an abandoned mine, a permanent stat building, a creature dwelling, a
  bank, a special building, down to a pickup on a spot too small for a building.
- One spot per map holds a dragon dwelling: Frozen Cliffs (azure dragon), Crystal Cavern
  (crystal dragon), Sulfurous Lair (rust dragon) or Magic Forest (faerie dragon). It is
  guarded as the map's top prize. It goes to the spot the homes reach last (A1).
- On seeds 1 to 10 at size 72, no run of free land sits farther than the remote distance
  from every object worth the walk once the map is done. The seed 4 snow cove and the
  seed 3 far island hold a landmark.
- Accent patches carry vegetation at the corpus share. The corpus patch cover is 58% against
  56% for the whole map. On seeds 1 to 10 at size 72 the generated patch median sits within
  the corpus patch p10 to p90.
- At least 84% of generated patches of 20 to 150 tiles hold a counted object, as the corpus
  does. That range is the corpus reading's, kept so both sides read alike. It limits the
  proof, never the generator.
- On seed 25 at size 144, the lava patch near (5,15) and the grass patch near (20,40) show
  trees and a landmark.

**Out of scope.**

- Where the remote spots come from. Vegetation leaves them, and this note fills them
  rather than closing them.
- Patches that touch a place boundary. The terrain model already keeps accents off it.
- The effort bands themselves. This note reads them and changes none.
- Mod terrains with no corpus vegetation model.

## 1b. Claims

1. Every gameplay object is placed after vegetation, and its body may stand over trees.
   (memory: gameplay after vegetation)
2. Each zone's object total follows the corpus rate. (memory: gameplay after vegetation)
3. Reward follows hero-days. Band 4 and up hold level 6 and 7 dwellings. The guard comes
   first and the value follows it. (memory: effort reward)
4. The catalog is the only source of object identity, and mod objects join through it.
   (AGENTS.md, memory: effort reward)
5. The landmark is a gold mine or an abandoned mine, a stat building or a dwelling, and a
   level 8 dwelling is better. (the user) The user then named the kind: "more like the azure
   dragon, crystal dragon, etc."
6. "We should not have a rule limiting the size or the terrain type for these kind of
   dwelling or landmark item." (the user, 2026-10-12)
7. "A market of time would also be worth it." (the user, 2026-10-12)
8. "We want to make every spot of a map being worth going to." (the user, 2026-10-12)
9. No space on the map may be abandoned, and the plan should give every open area its
   purpose early. (memory: no abandoned space)
10. No fixed tile buffers: every threshold derives from the map or the corpus. (memory: rules
    scale with map size)

Domain facts behind claim 5:

- The base game ships four dragon dwellings, one per neutral dragon. The game data gives
  the azure, crystal and rust dragons level 10, and the faerie dragon level 8. Every faction
  creature stops at level 7.
- Unlike the Golem Factory and the Elemental Conflux, the dragon dwellings carry no guard of
  their own. The map must guard them.
- The corpus holds 45 dragon dwellings on 15 of 159 maps: one map in ten has them, about
  three each.
- The Market of Time is an object of the original game, index 50, that the game never made
  work. The VCMI config ships it as "Unused/not implemented H3 object present on some RoE
  maps": a hero who visits it gets nothing.
- On the median corpus map, 3.7% of free land sits 3 or more king steps from every gameplay
  object, and 0.1% sits 4 or more. The p90 map leaves 18.7% and 4.7%.
- Inside corpus patches, counted objects split: mines 22%, permanent stat buildings 17%,
  dwellings 14%, temporary bonuses 10%, signs 9%, banks 7%, spells and skills 7%, towns 6%.

## 2. Parts and concepts

### Level 1: parts

1. **Spot census.** Finds the spots of a level. It owns which tiles form a spot and which
   place holds it. It never knows what grows or stands there. It acts at two moments. Once
   the terrain is painted, it finds the patches of another terrain, of any size. Once the
   map-wide gameplay pass is done, it finds the remote runs of free land. It hands each list
   to greening, landmark choice and siting.
2. **Patch greening.** Makes a patch grow the vegetation of its own terrain. It owns the
   rule that the ground under a tile picks the vegetation kind. It never knows about
   landmarks. It hands the grown map to siting, which reads which tiles stay open.
3. **Landmark choice.** Picks what each spot holds. It owns the ordered list of landmark
   kinds and the corpus weights. It never knows tiles. It hands a ranked list of identities
   per spot to siting, from the drawn kind down to the smallest object of any kind.
4. **Landmark siting.** Stands the first identity of the list that fits inside its spot with
   a reachable entrance. It owns the spot-first tile order. It never knows why the kind was
   chosen. It hands the placed object to the guard and reward work that already exists.
5. **Proof.** Measures generated patches against corpus patches: cover share, landmark rate,
   landmark mix. It owns the report. It never knows how the generator works.

Flow: the census finds the patches once the terrain is final. Greening reads them while
vegetation grows. Choice and siting stand a landmark on each patch first in the place's
gameplay turn, so it claims its patch before the place's other objects fill the space. The
map-wide pass then places the rest. The census finds the remote runs that pass left, and
choice and siting fill each one, the costliest to reach first. The dragon allowance reads
both lists. All of this ends before compensation, which then counts the landmarks' value.
Proof reads the finished map.

Test: a terrain painter that marks its own patches and a reader that floods them afterwards
both fit the census. A grower that switches model per tile and one that grows each patch as
its own little zone both fit greening.

### Level 2: concepts

**Patch census**

| Concept | Owns | Never knows |
|---|---|---|
| Spot | one spot: its tiles, its place, and its terrain when it is a patch | vegetation, objects |
| Remote distance | the king steps past which free land counts as remote, from the corpus (A7) | how spots are found |
| Patch census | the patches of another terrain on one level, of any size | objects |
| Remote census | the runs of reachable free land beyond the remote distance on one level | terrain |

**Patch greening**

| Concept | Owns | Never knows |
|---|---|---|
| Ground model choice | which terrain's vegetation model a tile samples | patches, landmarks |
| Patch growth | growing a patch's tiles with its own terrain's model, inside the place's budget | how the model was built |

**Landmark choice**

| Concept | Owns | Never knows |
|---|---|---|
| Landmark kind | the list: dragon dwelling, gold mine, abandoned mine, stat building, dwelling, bank, special building, pickup | identities |
| Kind weights | the corpus spot mix that weighs the kinds below the dragon dwelling (A5) | which content is enabled |
| Dragon allowance | which spot holds the map's dragon dwelling (A1) | the dwelling's identity |
| Landmark pool | the identities of one kind on one terrain, asked of the catalog | weights, spots |
| Fallback ladder | the drawn identity, then smaller ones of its kind, then the other kinds down to a pickup | tiles |

**Landmark siting**

| Concept | Owns | Never knows |
|---|---|---|
| Spot tile order | the spot's tiles ranked for a landmark, its heart first: the patch centre, or the remote tile farthest from every object | the kind |
| Landmark claim | one placed landmark | the census |

**Proof**

| Concept | Owns | Never knows |
|---|---|---|
| Patch reading | cover share and counted objects of one patch, on any map | generator or corpus origin |
| Patch report | corpus spread beside the generated spread | how either was made |

The spot is a shared value type: the census makes it, the other parts read it. The
catalog is the read-only reference every part consults.

## 3. Invariants

1. Every spot holds exactly one landmark, or the run logs why not. Owner: landmark claim.
   Upheld by: spot tile order, fallback ladder.
2. A landmark's entrance stands inside its spot and is reachable from a home. Its solid
   cells may spill onto the place around the spot. Owner: landmark claim.
3. A tile's vegetation comes from the model of the terrain under it. Owner: ground model
   choice.
4. A map holds at most one dragon dwelling from this feature, and it is guarded at the top
   guard level. Owner: dragon allowance.
5. A patch landmark counts inside the place total. A remote landmark adds to it, because
   the pass already spent the total and left the spot empty. Owner: landmark claim.
7. No spot rule names a tile count or a terrain. The remote distance comes from the corpus.
   Owner: remote distance. Upheld by: patch census, remote census.
6. Identity, footprint and terrain of every landmark come from the catalog. Owner: landmark
   pool.

## 4. Forces and patterns

**Forces.**

- The enabled content varies: base, HotA, Wake of Gods. A mod may add dwellings above
  level 7, so the dragon dwelling is "a dwelling whose creature is above level 7", not a
  list of names.
- The landmark kinds grow when a mod adds a kind. The order is the user's and changes rarely.
- Terrains vary per tile inside one place. Vegetation varies per terrain.
- Tests must build a patch from a few literal tiles, with no pipeline.
- Spots come from two sources that know different things: the painted terrain, and the
  objects the map-wide pass left. The first is known before gameplay, the second only after.
- A spot can be one tile or a hundred. What fits varies from a pickup to a 3x3 dwelling.
- Determinism: the same seed gives the same landmark.

**Between parts.** One value handed along: the census publishes the patch list once, and
greening, choice and siting read it. Force: three parts read one fact, and none may
recompute it differently.

**Inside parts.**

- Patch census, remote census, spot tile order, ground model choice: plain functions. The
  two censuses are two functions that return the same spot value. Force: the two sources
  know different things at different moments, and both feed the same choice and siting.
- Fallback ladder: a plain ordered list. Force: a spot's size varies from one tile up.
- Landmark kind: a plain ordered tuple. Its variation is the content, which the catalog
  answers, so no strategy is needed.
- Landmark pool: a catalog question. Force: claim 4, mod content joins through the catalog.
- Dragon allowance: a plain rule over effort (A1). Force: claim 3.

**Claims.**

Claims 6 to 10 are kept. Claim 6 drops the patch floor and the terrain test from the
generator. The ground rule stays: the catalog still says which identity may stand on which
terrain, so a lava-only object never lands on snow. Claim 7 is kept in the kind list as
"special building". The Market of Time joins it only through the catalog, and only when an
enabled mod makes it work (A9). Claim 9 is met by the patch census, which runs before
gameplay. The remote census is the safety net for what the plan missed.

1. Kept: siting runs inside gameplay, after vegetation.
2. Kept: the landmark counts inside the place total (invariant 5).
3. Kept: a dragon dwelling is a band-4 prize, so it goes to the patch the effort reading
   prices highest. It has no guard of its own, so the guard rule puts the top level in front
   of it.
4. Kept: new catalog questions for the abandoned mine and for a dwelling's creature level.
   The dragon dwellings come from that level, never from a name list.
5. Kept as the kind list.

**SOLID.** Each Owns reads without "and". A new landmark kind is one tuple entry and one
catalog question. No variant subclasses another. The consumers depend on the catalog port
alone.

## 5. Mapping onto the existing system

Revision log:

- R7. 2026-10-12, slice 5 build. The user saw the far island of seed 3 at size 72 hold a
  shipyard, a sign, a guard and a seal, and nothing worth the walk. The remote distance now
  counts only from objects worth the walk: a guard, a sign, a seal, a shipyard or a portal
  never makes land near it worth going to. Measured that way, the corpus distance grows
  with size: about 4 king steps at 36, 5 at 72 and 108, and 6 at 144, so A7 changed. The
  fill runs as its own step after the free piles and before compensation, so it sees every
  treasure, loot room and pile. Its kind list leaves out the gold mine, because gold mines
  follow their own corpus count and contest rule. A remote body keeps off the approach of
  every object already placed.
- R6. 2026-10-12, the user widened the problem (claims 6 to 8). Section 1 now covers every
  spot, not only accent patches. The patch floor (A2) is gone, and the census gains the
  remote runs and a second moment after the map-wide pass. The kind list gains banks,
  special buildings and pickups, and the fallback ladder reaches down to a pickup.
  Invariant 5 splits, and invariant 7 is new. The findings: `LANDMARK_FLOOR = 20`
  (`core/steps/gameplay/landmark.py:25`) and `dragon_order` (`landmark.py:72`) skip every
  patch under 20 tiles. The seed 4 snow cove is the zone's own snow, so `accents`
  (`core/reading/paint.py`) never lists it. The landmark pools hold no bank, special
  building or pickup (`landmark.py:59`). The catalog maps `MARKET_OF_TIME`, `BLACK_MARKET`,
  `ALTAR_OF_SACRIFICE` and `FREELANCERS_GUILD` to `SPECIAL` (`vcmi/catalog/tables.py:232`,
  `:354`), but no gameplay pool asks for `SPECIAL`, and the taxonomy holds no sprite for
  the Market of Time. The place roles stop at the terrain: the gameplay placer reads no
  role (`core/steps/gameplay/placer.py:145`), and nothing outside
  `core/planning/content.py` reads `PlaceIntent.role`, `scale` or `guard`. Loot rooms stop
  at 16 tiles (`core/grid/pockets.py:69`), so a larger cove inside a zone has no owner.

- R1. Census: "new" became "reshape". A reader already finds accents but drops their tiles.
- R2. The user named the dragon dwellings instead of the Wake of Gods level 8 ones. The mod
  price fallback is gone. The fix moved to the value table and the creature level question.
- R3. Slice 2 build: the permanent stat pool already answers `candidates(STAT_PERMANENT, t)`,
  so no new catalog question was needed. The patch census runs under the markov model too,
  because its flood places also carry a dominant terrain. The smaller-object fallback moved
  out of `gameplay/step.py` into `placement/fallback.py`, so the landmark, the attractions
  and the remote fill share it. The core may not name the VCMI type of the abandoned mine, so its guard level
  stays at the default 3.
- R4. Slice 3 build: the dragon allowance reads travel days only, because no gate guard or
  monster stands yet when the gameplay step places it. The step places the shipyards before
  the dragon, so a home across a river still reaches the far patches. The dragon tries the
  patches from the costliest down and stands on the first with room, carrying its own
  level-7 guard. The drawer and the landmark pools leave out every dwelling above level 7,
  so the dragon dwelling comes only from the allowance. Few maps have a patch of 20 tiles or
  more: on seeds 1 to 10 at size 72 only seeds 5, 9 and 10 do, and each of them shows one
  dragon dwelling. On seed 25 at size 144 both patches are too thin and wooded for a 3x3
  dwelling, so that map has none. The dirt patch at (3, 16) there fits no landmark at all:
  it is a thin strip at the shore, covered by its own trees.
- R5. Slice 4 build: the report reads patches by the corpus rule, a same-terrain land
  component of 20 to 150 tiles whose rim is at least 70% one land terrain, on both sides.
  It needs no place labels, so it reads a corpus map and a generated one alike. On seeds 1
  to 10 at size 72 it finds 11 generated patches. Each holds a counted object, against 84%
  in the corpus. Their cover median is 43%, inside the corpus p10 to p90 of 37% to 79% but
  below its 59% median. Mines and dwellings take 68% of the counted objects inside them,
  against 36% in the corpus, because the landmark pool holds only mines, stat buildings and
  dwellings. Three of the 10 maps stand a dragon dwelling, against 15 of 159 corpus maps.

**Remote census: new (R6, R7)**, beside the patch census in `core/reading/remote.py`. The
distance reading `object_distance` moves from the compensation step to
`core/grid/distance.py`, so both steps share it. The census measures king steps to the
nearest object worth the walk and floods the free tiles past the remote distance into runs.
The fill is its own step, `core/steps/remote/`, after scatter and before compensation (R7).
The remote distance per map size is a corpus prior in `data/pp/remote.json`.

**Patch census: reshape (R1, R6).** `LANDMARK_FLOOR` and its checks go. The corpus patch
reading in `core/reading/patches.py` keeps its 20 to 150 range, because it serves the proof
only. `core/reading/paint.py:204` `accents` finds the same
components but returns only place, terrain and size (`Accent`, line 24). It gains the tile
set. The terrain step publishes the list beside `LevelPlaces` in `terrain_gen/result.py`.
The markov model publishes its flood places' accents as well (R3).

**Patch greening: reshape.** `core/steps/vegetation/grow.py:51` and `:70` pick one model per
zone from `zone.terrain`. The ground rule in the sampler options then refuses every tree on
an accent tile, so the patch stays bare. The fix samples each patch with its own terrain's
model inside the zone's budget. The sampler protocol stays as it is.

**Landmark choice: new**, in `core/steps/gameplay/landmark.py`. Mismatches with the catalog:

- `mines_by_resource` drops the abandoned mine (`vcmi/catalog/adapter.py:107`). The gold mine
  is there under "gold". A new port method answers the abandoned mines on a terrain.
- The four dragon dwellings already reach `candidates(DWELLING, t)` on every land terrain
  (`avgazur`, `avgcdrg`, `avgrust`, `avgfdrg`). The drawer can pick one today, at random,
  as an ordinary dwelling.
- `creature_level` clamped to 7 when this was written, although
  `data/catalog/monster_levels.json` holds 10 for the azure, crystal and rust dragons and 8
  for the faerie dragon. A new port method answers a dwelling's creature level, unclamped.
  The dragon pool is every dwelling whose level is above 7. Since 2026-10-11 the stack
  level is unclamped too, and the dragons guard at levels 8 to 10.
- The value table prices every fixed dwelling at 2000 (`core/reading/value.py:24`), the same
  as a goblin barracks. Only the random dwellings get 1000 per level (`value.py:30`). The
  code is wrong here: a fixed dwelling should take 1000 per creature level as well, so a
  Frozen Cliffs reads 10000. That moves it into the top effort band and brings the top guard.
- The permanent stat building pool already exists as `candidates(STAT_PERMANENT, t)` (R3).

**Landmark siting: exists, with a new spot order.** `core/placement/site.py:381`
`ZoneSite.place(purpose, ident, centres)` already checks stands, reach and doors. The landmark
passes the patch tiles first as `centres`. `place_attractions` (`gameplay/step.py:128`)
already drops items when the site has spent slots, so the landmark counts by raising
`site.spent` by one before the other attractions.

**Proof: new**, a `cli/` report beside `readings`, reusing the patch reading on corpus and
generated maps alike. The scripts that measured the corpus numbers in section 1 become its
seed.

**The system has, the design lacks.** The smaller-object fallback in `place_attractions`.
The design missed it: a landmark that does not fit falls back to a smaller identity of the
same kind before moving down the kind list.

## 6. Slices

1. **Greening.** Ground model choice and patch growth. Done when seed 25 at size 144 shows
   trees on both patches, and the patch cover median on seeds 1 to 10 sits inside the corpus
   p10 to p90.
2. **Base landmark.** Census with tiles, kind list without the dragon, spot order, claim.
   Done when every patch of 20 tiles or more on seeds 1 to 10 holds a landmark, and golden
   hashes are regenerated.
3. **Dragon dwelling.** Creature level question, fixed dwelling price, allowance. Done when
   each of seeds 1 to 10 shows one dragon dwelling in a patch, behind a top-level guard.
4. **Proof report.** Done when the report prints corpus against generated for cover, landmark
   rate and mix.
5. **Remote fill (R6, R7).** Remote distance per map size, remote census, spot tile order
   for a remote run, the fallback ladder down to a pickup, in a step of its own after the
   free piles. The seed 3 far island at size 72 holds a landmark. Done when the seed 4 snow cove at size 72 holds a
   landmark, and seeds 1 to 10 at size 72 leave no free tile at the remote distance from
   every gameplay object. `make check` passes and golden hashes are regenerated.
6. **No floor (R6).** Drop the patch floor, so every patch of any size gets a landmark, the
   smallest ones a pickup. The dragon allowance reads patches and remote runs alike. Done
   when seeds 1 to 10 at size 72 each show one dragon dwelling, and the log names no patch
   left empty.
7. **Wider kinds (R6).** Banks, special buildings and their corpus weights in the kind list,
   each through a catalog question. Done when the patch report's purpose mix inside patches
   moves toward the corpus: banks, signs and spells appear, and mines fall from 43% toward
   22%.

## 7. Assumptions

1. **Assumption:** a dragon dwelling belongs only to the patch with the highest hero-day
   price on the map, one per map.
   **Decided:** the allowance picks that one patch.
   **Basis:** the user's "even better" and claim 3. A weekly azure dragon outclasses every
   band-4 prize. The corpus is rarer, one map in ten, but three per map where they appear.
   **If wrong:** dragon allowance, invariant 4, slice 3.
2. **Assumption (revised R6):** a spot of any size can hold something worth the walk.
   **Decided:** no floor. A spot too small for a building takes the largest object the
   fallback ladder fits, down to a one-tile pickup.
   **Basis:** the user's claim 6. The old floor of 20 came from the corpus sample's own
   lower bound, which describes the reading, not the game.
   **If wrong:** fallback ladder, invariant 1, slice 6.
3. **Assumption:** a dragon dwelling priced at 10000, or 8000 for the faerie dragon, sits
   in the top effort band.
   **Decided:** every fixed dwelling takes 1000 per creature level.
   **Basis:** `core/reading/value.py:30`. The change also raises every fixed level 5 to 7
   dwelling above its current 2000, so their guards grow too.
   **If wrong:** the fixed dwelling price, slice 3.
4. **Assumption:** a landmark counted inside the place total leaves the place's other
   objects in balance.
   **Decided:** the landmark takes one of the drawn slots.
   **Basis:** the corpus density inside patches matches the map, 3.03 against 2.92 per 100
   tiles.
   **If wrong:** landmark claim, invariant 5.
5. **Assumption:** the kind weights below the dragon dwelling follow the corpus patch mix: mines 166,
   stat buildings 132, dwellings 112, read from 359 corpus patches.
   **Decided:** gold and abandoned mines split the mine weight evenly. Slice 7 adds banks,
   special buildings and pickups at their own corpus shares inside patches.
   **Basis:** the corpus count. The split is a guess.
   **If wrong:** kind weights.
6. **Assumption:** the proof runs in minutes on seeds 1 to 10 at size 72.
   **Decided:** done-when measures there, plus the one seed 25 run at 144.
   **Basis:** the current size 72 run time.
   **If wrong:** slices 1 to 4 done-when.
7. **Assumption (revised R7):** the remote distance grows with map size, as the corpus
   shows: 4 king steps at size 36, 5 at 72 and 108, 6 at 144.
   **Decided:** free land at the remote distance or more from every object worth the walk
   counts as remote. The distance is the smallest step count at which the median corpus
   map of that size leaves under 0.1% of its free land. A map size between corpus sizes
   takes the nearest one. Guards, signs, seals, shipyards and portals do not count.
   **Basis:** the corpus reading counted only from objects worth the walk. Median share of
   free land at 4 or more steps: 0 at 36 (31 maps), 1.14% at 72 (71 maps), 1.24% at 108
   (38 maps). At 5 or more: 0 at 72, 0.08% at 108, 0.15% at 144 (19 maps). At 6 or more:
   0.06% at 144.
   **If wrong:** remote distance, remote census, slice 5.
8. **Assumption:** every map holds one dragon dwelling.
   **Decided:** the allowance picks the costliest spot on every map, now that every map has
   spots.
   **Basis:** the user named a dragon dwelling for the seed 4 cove. The corpus has them on
   one map in ten, three each, so this map-level rate runs above the corpus.
   **If wrong:** dragon allowance, slice 6.
9. **Assumption:** the Market of Time joins only when an enabled mod makes it work.
   **Decided:** the special building kind asks the catalog, and the base content answers
   no Market of Time.
   **Basis:** the VCMI config marks it unused and not implemented, and the catalog
   taxonomy holds no sprite for it.
   **If wrong:** landmark pool, slice 7, and a catalog entry through `regen-ontology`.
