# Map generator, designed from the problem

Sections 1 to 4 were written from the problem statement and the root `AGENTS.md` alone.
No source, test, data or `docs/` file was open before section 4 was finished. Two things
sat in context before the design started: the root `AGENTS.md` module list, and a one-line
memory note saying gameplay is placed after vegetation. Each concept below passed the test
"would I have named this without having seen the code?". The ordering of vegetation before
gameplay objects is derived in section 4 from the back-contact measure, not taken from the
memory note.

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
| Object Catalog | What an object type is: identity, footprint, visitable tiles, allowed terrain | How often the corpus places it |
| Corpus Map | One real map read from `.h3m` into the same shape a generated map has | Statistics over the corpus |
| Placement Measure | One number that describes where a placed object sits on a map | Whether the map is real or generated |
| Corpus Priors | The corpus spread of counts and measures per object type and terrain | What an object type is (Object Catalog) |
| Zone Layout | Which zone owns each tile on each level, water bodies included | Objects |
| Passage | A crossable stretch of shared border between two zones | What guards it (Guard) |
| Terrain | The terrain type of each tile | Which frame a tile shows (Tile Appearance) |
| Tile Appearance | The frame each tile shows, given its neighbours | Why a tile has its terrain type |
| Walkable Web | The set of tiles that must stay passable | Which object stands where |
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
3. Zone Layout partitions each level. Terrain paints each zone. Passage picks the
   crossable stretches of each shared border.
4. Player Setup assigns a start zone per player. Walkable Web reserves the tiles that link
   start sites and passages.
5. Vegetation fills the land in the terrain's texture and leaves the web open.
6. Object Quota sets each zone's counts from Corpus Priors. For each object, Site Rules
   filters the candidate tiles, and Site Choice scores the survivors with Placement
   Measure against Corpus Priors. The Map takes the object, and Walkable Web extends to
   its visitable tile.
7. Guard sizes a monster for each guarded passage, mine and treasure. Pickups follow the
   same path as other objects.
8. Tile Appearance fixes frames. Map Export writes the `.vmap`, and Map Picture writes the
   PNG.
9. Realism Verdict runs Placement Measure over generated maps and compares with Corpus
   Priors.

## 3. Invariants

| Invariant | Enforced by |
|---|---|
| An object's identity, footprint, visitable tiles and allowed terrain come only from the game's object table | Object Catalog |
| Corpus Priors carries counts and spreads keyed by identity, never a footprint or a terrain rule | Corpus Priors |
| Every object stands on terrain its type allows | Map, on insertion |
| No object covers another object's visitable tile | Map, on insertion |
| No blocking tile lands on a reserved tile | Map, on insertion |
| Reserved tiles connect every start town to every passage and every visitable tile, with guard tiles counted as passable | Walkable Web |
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
  "done" check compares them, so a drift between two implementations fakes a pass.
- F4. A developer changes one stage and must see the result in under 20 seconds at size
  72. Changing one stage must not reshuffle the draws of every other stage, or the
  comparison shows noise.
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
| Random Stream | Plain function from request and stage name to a seeded generator | F4 |
| Object Catalog | Plain value type, loaded from the editor table | F1 (kept apart from priors; no variation of its own) |
| Corpus Map | Adapter that yields a Map | F3 (measures read one type) |
| Placement Measure | Dict of named measure functions, shared by corpus and generated sides | F3 |
| Corpus Priors | Cache stored as data, keyed by corpus and measure version | F2 |
| Zone Layout, Terrain, Passage | Plain functions inside their stage | none |
| Tile Appearance | Plain function | none |
| Walkable Web | Plain value type: a tile set with a connectivity check | none |
| Vegetation | Plain function, parameterised by per-terrain texture data | F9 |
| Player Setup | Plain value type | none |
| Object Quota | Plain function of zone area and corpus rate | none |
| Site Rules | Universal rules as one function, plus a dict of extra predicates keyed by family | F5, F7 |
| Site Choice | Weighted sum of term functions, one term per measure | F6 |
| Guard | Plain function of value | none |
| Map | Plain type that checks its three insertion invariants | none |
| Map Export | Plain function over the Map | none |
| Map Picture | Plain function, sprite archive passed in | F8 (tests skip, so no port) |
| Realism Verdict | Oracle: measure, reference, tolerance and verdict as separate parts | F3 |
| Generation Run | Pipeline of stages with typed outputs, stop-after and per-stage streams | F4, F11 |

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
