# Accent landmarks

Disclosure: before this note was started I had read the vegetation grower and its sampler,
the gameplay drawer and step, the zone site, the catalog port and its VCMI adapter, and the
mod object reader. Three settled designs from memory also loaded: gameplay after
vegetation, effort reward, and decompose before coding. Their decisions are claims in 1b.

## 1. Problem

**Who feels it.** A player crossing a big place finds a small patch of another terrain, a
lava pool in rough ground or a meadow in dirt, and the patch is bare: no trees, no rocks, no
building. It reads as a hole in the map rather than a spot worth the walk.

**Done looks like.**

- Every accent patch of 20 tiles or more holds one landmark: a gold mine, an abandoned mine,
  a permanent stat building or a creature dwelling.
- One patch per map holds a dragon dwelling: Frozen Cliffs (azure dragon), Crystal Cavern
  (crystal dragon), Sulfurous Lair (rust dragon) or Magic Forest (faerie dragon). It is
  guarded as the map's top prize.
- Accent patches carry vegetation at the corpus share. The corpus patch cover is 58% against
  56% for the whole map. On seeds 1 to 10 at size 72 the generated patch median sits within
  the corpus patch p10 to p90.
- At least 84% of generated patches of 20 to 150 tiles hold a counted object, as the corpus
  does.
- On seed 25 at size 144, the lava patch near (5,15) and the grass patch near (20,40) show
  trees and a landmark.

**Out of scope.**

- The wide clearing in a home place, such as the one around (5,135) on seed 25. It is a
  separate problem about open ground, parked for its own decision.
- Patches that touch a place boundary. The terrain model already keeps accents off it.
- The effort bands themselves. This note reads them and changes none.
- Mod terrains with no corpus vegetation model.

## 1b. Claims

1. Every gameplay object is placed after vegetation, and its body may stand over trees.
   (memory: gameplay after vegetation)
2. Each zone's object total follows the corpus rate. (memory: gameplay after vegetation)
3. Reward follows hero-days. Band 4 holds level 6 and 7 dwellings. The guard comes first and
   the value follows it. (memory: effort reward)
4. The catalog is the only source of object identity, and mod objects join through it.
   (AGENTS.md, memory: effort reward)
5. The landmark is a gold mine or an abandoned mine, a stat building or a dwelling, and a
   level 8 dwelling is better. (the user) The user then named the kind: "more like the azure
   dragon, crystal dragon, etc."

Domain facts behind claim 5:

- The base game ships four dragon dwellings, one per neutral dragon. The game data gives
  the azure, crystal and rust dragons level 10, and the faerie dragon level 8. Every faction
  creature stops at level 7.
- Unlike the Golem Factory and the Elemental Conflux, the dragon dwellings carry no guard of
  their own. The map must guard them.
- The corpus holds 45 dragon dwellings on 15 of 159 maps: one map in ten has them, about
  three each.

## 2. Parts and concepts

### Level 1: parts

1. **Patch census.** Finds the accent patches of a level once the terrain is painted. It
   owns which tiles form a patch and which place encloses it. It never knows what grows or
   stands there. It hands the patch list to greening, landmark choice and siting.
2. **Patch greening.** Makes a patch grow the vegetation of its own terrain. It owns the
   rule that the ground under a tile picks the vegetation kind. It never knows about
   landmarks. It hands the grown map to siting, which reads which tiles stay open.
3. **Landmark choice.** Picks what each patch holds. It owns the ordered list of landmark
   kinds and the corpus weights. It never knows tiles. It hands one identity per patch to
   siting.
4. **Landmark siting.** Stands the chosen landmark inside its patch with a reachable
   entrance, and counts it inside its place's total. It owns the patch-first spot order. It
   never knows why the kind was chosen. It hands the placed object to the guard and reward
   work that already exists.
5. **Proof.** Measures generated patches against corpus patches: cover share, landmark rate,
   landmark mix. It owns the report. It never knows how the generator works.

Flow: the census runs once the terrain is final. Greening reads the census while vegetation
grows. Choice reads the census and the enabled content before gameplay places anything in
the place. Siting runs first in the place's gameplay turn, so the landmark claims its patch
before the place's other objects fill the space. Proof reads the finished map.

Test: a terrain painter that marks its own patches and a reader that floods them afterwards
both fit the census. A grower that switches model per tile and one that grows each patch as
its own little zone both fit greening.

### Level 2: concepts

**Patch census**

| Concept | Owns | Never knows |
|---|---|---|
| Accent patch | one patch: its tiles, its terrain, its enclosing place | vegetation, objects |
| Patch floor | the smallest patch that earns a landmark (A2) | how patches are found |
| Census | the list of patches on one level | the floor's value |

**Patch greening**

| Concept | Owns | Never knows |
|---|---|---|
| Ground model choice | which terrain's vegetation model a tile samples | patches, landmarks |
| Patch growth | growing a patch's tiles with its own terrain's model, inside the place's budget | how the model was built |

**Landmark choice**

| Concept | Owns | Never knows |
|---|---|---|
| Landmark kind | the ordered list: dragon dwelling, gold mine, abandoned mine, stat building, dwelling | identities |
| Kind weights | the corpus patch mix that weighs the kinds below the dragon dwelling | which content is enabled |
| Dragon allowance | which patch holds the map's dragon dwelling (A1) | the dwelling's identity |
| Landmark pool | the identities of one kind on one terrain, asked of the catalog | weights, patches |

**Landmark siting**

| Concept | Owns | Never knows |
|---|---|---|
| Patch spot order | the patch's tiles ranked for a landmark, the patch centre first | the kind |
| Landmark claim | one placed landmark, counted inside the place total | the patch census |

**Proof**

| Concept | Owns | Never knows |
|---|---|---|
| Patch reading | cover share and counted objects of one patch, on any map | generator or corpus origin |
| Patch report | corpus spread beside the generated spread | how either was made |

The accent patch is a shared value type: the census makes it, the other parts read it. The
catalog is the read-only reference every part consults.

## 3. Invariants

1. Every patch at or above the floor holds exactly one landmark, or the run logs why not.
   Owner: landmark claim. Upheld by: patch spot order.
2. A landmark's solid cells stand inside its patch or on its enclosing place, and its
   entrance is reachable from the place's roads. Owner: landmark claim.
3. A tile's vegetation comes from the model of the terrain under it. Owner: ground model
   choice.
4. A map holds at most one dragon dwelling from this feature, and it is guarded at the top
   guard level. Owner: dragon allowance.
5. The landmark counts inside the place total, so the place holds no more objects than its
   corpus rate allows. Owner: landmark claim.
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
- Determinism: the same seed gives the same landmark.

**Between parts.** One value handed along: the census publishes the patch list once, and
greening, choice and siting read it. Force: three parts read one fact, and none may
recompute it differently.

**Inside parts.**

- Census, spot order, ground model choice: plain functions. No variation.
- Landmark kind: a plain ordered tuple. Its variation is the content, which the catalog
  answers, so no strategy is needed.
- Landmark pool: a catalog question. Force: claim 4, mod content joins through the catalog.
- Dragon allowance: a plain rule over effort (A1). Force: claim 3.

**Claims.**

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

- R1. Census: "new" became "reshape". A reader already finds accents but drops their tiles.
- R2. The user named the dragon dwellings instead of the Wake of Gods level 8 ones. The mod
  price fallback is gone. The fix moved to the value table and the creature level question.
- R3. Slice 2 build: the permanent stat pool already answers `candidates(STAT_PERMANENT, t)`,
  so no new catalog question was needed. The patch census runs under the markov model too,
  because its flood places also carry a dominant terrain. The smaller-object fallback moved
  out of `gameplay/step.py` into `gameplay/fallback.py`, so the landmark and the attractions
  share it. The core may not name the VCMI type of the abandoned mine, so its guard level
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

**Patch census: reshape (R1).** `core/reading/paint.py:204` `accents` finds the same
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
- `creature_level` clamps to 7 (`adapter.py:135`), although `data/catalog/monster_levels.json`
  holds 10 for the azure, crystal and rust dragons and 8 for the faerie dragon. A new port
  method answers a dwelling's creature level, unclamped. The dragon pool is every dwelling
  whose level is above 7.
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

## 7. Assumptions

1. **Assumption:** a dragon dwelling belongs only to the patch with the highest hero-day
   price on the map, one per map.
   **Decided:** the allowance picks that one patch.
   **Basis:** the user's "even better" and claim 3. A weekly azure dragon outclasses every
   band-4 prize. The corpus is rarer, one map in ten, but three per map where they appear.
   **If wrong:** dragon allowance, invariant 4, slice 3.
2. **Assumption:** 20 tiles is the floor.
   **Decided:** smaller patches get greening only.
   **Basis:** the corpus sample starts at 20, and a 3x3 dwelling with its approach needs
   about 12 tiles.
   **If wrong:** patch floor, invariant 1, slice 2.
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
   **Decided:** gold and abandoned mines split the mine weight evenly.
   **Basis:** the corpus count. The split is a guess.
   **If wrong:** kind weights.
6. **Assumption:** the proof runs in minutes on seeds 1 to 10 at size 72.
   **Decided:** done-when measures there, plus the one seed 25 run at 144.
   **Basis:** the current size 72 run time.
   **If wrong:** slices 1 to 4 done-when.
