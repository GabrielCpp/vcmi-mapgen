# Global gameplay placement

**Disclosure.** I read the existing system before writing this note. The grill that settled
the design read the gameplay step, the zone site, the guards, the roads, the effort and
route readings, the loot pockets and the corpus miners. The settled decisions sit in a
memory note. Every decision that reached me that way is a claim in section 1b. Sections 2
to 4 were checked against the test "would I have named this without having seen the
code?". Where a concept matches an existing one, section 5 says so.

## 1. Problem

**Who feels it.** A player opens a generated map and finds no crystal or gem mine anywhere
within two weeks of travel from the starting town. Another player on the same map has
both next door. The objects that are there look dropped on open ground. A hand-made map
tucks them into holes and corners, against trees and against cliffs, and keeps roads off
them.

**Done looks like.**

- Every player reaches a mine of each of the six basic resources within 14 hero-days of
  the starting town, guard fights included. This holds on 10 of 10 sweep seeds, on both
  terrain models.
- For each resource, the nearest mine of one player is at most 3 days farther than the
  nearest mine of another.
- No gold mine stands within 14 days of any player.
- About 2 in 3 objects stand with closed flanks, as on the corpus.
- Objects sit snug for their size as often as on the corpus: a one-tile object in a hole or
  a corner, a two-tile object with its far end against something, a larger one with its
  top against something.
- A road crosses an object it does not lead to for at most 6% of objects, the corpus
  share. Today it does for 9.4%.
- The map holds as many objects per walkable tile as the corpus, times a density setting
  that defaults to 1.

**Out of scope.**

- How much walkable ground vegetation leaves.
- Guards on wood and ore beyond the guaranteed copy. The corpus leaves 72% of them
  unguarded.
- Guard levels for objects other than mines.
- Carved underground gate sites.
- Treasure, loot, sets and quests. They keep their own placers and see the map after
  gameplay placement.

## 1b. Claims

Source for C1 to C24: the settled grill, 2026-10-05. Source for C25 to C28: the existing
code. Source for C29 and C30: the user, 2026-10-05, after slice 3.

1. Each player gets the six basic mines within 14 hero-days of the starting town. The
   days count travel and the guard toll on the shortest effort route. The mine may stand
   in any zone.
2. Two players may share a mine. The per-resource gap between players is at most 3 days.
3. A guaranteed rare mine has a level 3 guard. A guaranteed wood or ore mine has a level 1
   guard. Extra copies keep the guard their rarity sets.
4. Gold is optional. It never stands within 14 days of any player, and farther is better.
   A landmark gold mine counts.
5. Mines go first. When no spot fits inside 14 days, the mine takes the nearest spot
   beyond and a warning prints.
6. Later steps may not push a guaranteed mine past 14 days.
7. Rather than fail, the placer adds or swaps a mine.
8. One placer works over the whole map. It owns neutral towns, mines, dwellings, banks,
   visitables and accent landmarks. Player towns, gates and shipyards go before it.
9. The map-wide total follows the corpus rate per walkable tile. A CLI density multiplier
   scales it, default 1.0.
10. Zones decide terrain only. The hop reward scale no longer drives gameplay counts.
11. A new corpus miner reads effort from home per object family: travel days and the
    guards on the way, without the object's own guard. A family is a purpose, a mine
    resource or a dwelling level.
12. Each player gets the same count per family per band, within one.
13. The hardest objects go first.
14. On a shortage the placer places fewer and warns.
15. An object's mask is its blocking cells, its entrance and the tile in front. The sprite
    overhang may overlap vegetation, both ways.
16. Object bodies stay off the vegetation web.
17. A spot scores back cover, flank cover and hole fill. The map is checked against the
    corpus closed-flank share, about 2 in 3.
18. When the best spot has an open flank and the map is below that share, the placer plants
    a matching decoration on the flank at commit. There is no separate dressing pass.
19. Pockets are spots. A pocketed object has one guard in the pocket mouth at the object's
    level. For a mine it replaces the front guard.
20. Gameplay objects, treasure and loot draw from one pool of spots. Gameplay goes first.
21. Mine seals stay.
22. A road keeps off the whole sprite and the entrance tile of every object it does not
    lead to. In a pass with no other way it may cross, at a high price.
23. Roads may cross guards.
24. The guarantee is asserted on one seed in `make test` and on ten seeds in `make sweep`,
    on both terrain models. A fallback past 14 days fails the test seeds.
25. Gameplay bodies keep 2 tiles apart.
26. Each zone draws its own count from its area, its terrain's densities and its planned
    reward scale.
27. A neutral town brings two extra mines.
28. A random dwelling takes the faction of its zone's town.
29. A spot fits by the object's size. A one-tile object fits any hole, any corner and any
    L-shaped corner. A two-tile object fits left or right of vegetation, with the vegetation
    on the side away from its visit tile. A larger object fits with its top against
    vegetation, or in an open field.
30. There are no pockets and no mouth guards. Only mines carry a guard, in front. Mines are
    three tiles, so they never need a nook. Every object stays reachable, so its guard can
    stand in front.

## 2. Parts and concepts

### Level 1: parts

1. **Targets.** What hand-made maps teach about where objects stand. It owns, per object
   family, how far from home the corpus puts it, how many stand per walkable tile, and how
   often an object's flanks are closed. It never knows a generated map. It hands its tables
   to Allocation and to Accounting.
2. **Reach.** How many hero-days each player needs to get anywhere. It owns one effort
   field per player home. It never knows object families or targets. It hands the fields
   to Allocation and to Accounting.
3. **Spot survey.** Where an object's shape fits snugly on the ground as it stands. It owns
   the spots for a shape, each with its cover and whether it sits snug for its size. It never knows
   effort, families or which object will take the spot. It hands spots to Allocation.
4. **Allocation.** What goes where. It owns the list of objects to place, their order, and
   the one spot each takes. It never knows how spots are found or how effort is measured.
   It hands each choice to Standing.
5. **Standing.** Putting one object on the map. It owns the cells it claims, its guard, its
   seals and its flank decoration, and it keeps the rest of the map reachable. It never
   knows why the object stands there. It hands the changed ground back to Spot survey.
6. **Road courtesy.** Roads keep off objects they do not serve. It owns the price of a road
   step across an object's sprite or entrance. It never knows families or effort.
7. **Accounting.** Whether the finished map keeps its promises. It owns the per-player mine
   check and the shortfall tally. It never knows how objects were placed.

**Flow.**

- Before any generation, Targets reads the corpus once and stores its tables.
- When player towns, gates and shipyards stand, Reach prices the map from each home.
- Allocation lists the objects. It takes the guaranteed mines first. For each object it asks
  Spot survey for spots, filters them by the effort band the target wants, and picks one.
  Standing puts the object on the map, and Spot survey reads the changed ground for the
  next object.
- After the guaranteed mines, Reach prices the map again. Accounting checks the promise.
  Allocation repairs a broken promise by adding or swapping a mine.
- After all gameplay objects stand, Accounting checks the promise again and tallies the
  shortfall.
- When roads are laid, Road courtesy prices each step.
- When the whole map is done, Accounting checks the promise a last time. In a test a breach
  fails. In a run it warns.

A child could follow this: we learn from good maps how far things should be, we measure how
far each player has to walk, we look for snug places, we decide what goes in each place, we
build it, we keep roads polite, and we check that every player got their mines.

### Level 2: concepts

**Targets**

| Concept | Owns | Never knows |
|---|---|---|
| Home effort reading | The effort from the nearest player home to each corpus object, without its own guard | Bands |
| Target band | Per family, the share of objects in each effort band | Generated maps |
| Density | Per family and terrain, the objects per walkable tile | Effort |
| Flank share | The corpus share of objects whose flanks are closed | Families |

Family, Band and Effort are shared value types. Targets, Allocation and Accounting all read
them.

**Reach**

| Concept | Owns | Never knows |
|---|---|---|
| Home | One player's starting town visit tiles | Other players |
| Toll | The days a guard of each level costs | Routes |
| Reach field | The hero-days from one home to each tile, travel plus toll | Families, promises |

**Spot survey**

| Concept | Owns | Never knows |
|---|---|---|
| Shape | An object's mask: blocking cells, entrance and the tile in front | The sprite overhang |
| Ground | The tiles a body may cover: off other bodies, off the vegetation web, off kept rooms | Which object asks |
| Spot | An anchor where a shape fits the ground | Effort |
| Cover | A spot's score from its back and its flanks, the tiebreak among equal spots | Families |
| Snug fit | Whether a shape at a spot sits snug for its size class | Effort |

Snug fit replaced Pocket. See R13.

The spot pool of claim C20 is not a concept here. Revised, see R1.

**Allocation**

| Concept | Owns | Never knows |
|---|---|---|
| Promise list | For each basic resource, the spots that bring every player within 14 days at the smallest gap | Other families |
| Quota | Per family, how many objects the map holds | Spots |
| Band plan | Per family, how many objects each player gets in each band | Spots |
| Held reach | Per family and player, the objects that player reaches within each band | Spots |
| Order | Which object goes next | Bands |
| Siting | The one spot an object takes, by even reach, then band, then cover | How spots are found |
| Identity pick | Which object of a family stands on a spot, by its terrain and its size | Effort |
| Repair | The mine to add or swap when the promise breaks | Spot scoring |

Identity pick was added. See R6. Held reach was added. See R8.

**Standing**

| Concept | Owns | Never knows |
|---|---|---|
| Claim | The cells an object takes | Why it stands there |
| Guard post | Where an object's guard stands and at what level | Spot scoring |
| Seal | The blocking decorations beside a mine's entrance | The guard |
| Flank filler | A decoration matching the terrain on an open flank | Families |
| Reach keeper | Refusing a commit that strands walkable ground | Families |
| Zone record | The zone each placed object reports to | Allocation |
| Town tie | The town a random dwelling takes its faction from | Spots |

Zone record and Town tie were added. See R2 and R3.

Guard post stands a mine's guard on the tile in front of its entrance. It has one way to
do it. Revised, see R13.

**Road courtesy**

| Concept | Owns | Never knows |
|---|---|---|
| Served objects | The objects a road leads to | Prices |
| Courtesy price | The extra price of a step on the sprite or entrance of an object not served | Families |

**Accounting**

| Concept | Owns | Never knows |
|---|---|---|
| Promise check | Per player and basic resource, the nearest mine's effort and the gap between players | Repair |
| Shortfall tally | Per family, the quota against the count placed | Spots |

Shortfall tally moved here from Allocation. See R7.

## 3. Invariants

1. Every player reaches a mine of each basic resource within 14 hero-days. **Owner:**
   Promise check. Upheld by Promise list, Repair and Reach keeper.
2. For each basic resource, the gap between players is at most 3 days. **Owner:** Promise
   check. Upheld by Promise list.
3. No gold mine stands within 14 days of any player, its own guard counted. **Owner:**
   Promise check. Upheld by Guard post. See R10.
4. No body covers another body, the vegetation web, or another object's entrance or front
   tile. **Owner:** Claim. Upheld by Ground and Shape.
5. Every tile a hero could walk before a commit stays reachable after it. **Owner:** Reach
   keeper. Upheld by Seal and Flank filler, which ask it first.
6. Within each band, the objects of a family each player reaches differ by at most one
   between players at the moment each object stands. **Owner:** Siting, which skips an
   object that would break it. Upheld by Held reach. See R8 and R9.
7. The map never holds more objects of a family than its quota. **Owner:** Quota. Upheld by
   Siting.
8. A road crosses an object it does not serve only where no other way exists. **Owner:**
   Courtesy price.

## 4. Forces and patterns

**Forces.**

- F1. Two terrain models draw different zone shapes. Placement must work the same on both.
- F2. Pricing the map is not free. One player's reach field costs about 60 ms on a 72-tile
  map and about 290 ms on a 144-tile map (measured, seed 3, 4 homes: 0.25 s and 1.16 s).
  Re-pricing after each of 50 commits on a 144 map costs a minute.
- F3. Object families grow. Mods add objects, and the catalog switches them on and off.
- F4. The corpus is not uniform. The user wants the density tunable.
- F5. The guarantee must be checked in a test without running the placer twice.
- F6. Spot scoring must be testable on a hand-drawn grid, without effort or a catalog.
- F7. Treasure and loot find their own spots after gameplay, from the map as it stands.
- F8. The snug rule varies with the object's size: a hole or a corner for one tile, a
  closed far end for two, a closed top for three or more. Revised, see R13.
- F9. Downstream steps read results per zone.

**Between parts.**

- A sequence of moments with one value handed along: the map as it stands, plus the reach
  fields (F1). No part reads a zone's shape. Zones reach only Zone record.
- Reach is priced three times, not per commit (F2): after the fixed objects, after the
  guaranteed mines, and on the finished map.
- The Catalog stays the only source of object facts (F3).

**Inside parts.**

- Targets: plain tables keyed by family (F3). No per-family code.
- Quota: a plain function of walkable tiles, density and the multiplier (F4).
- Spot survey: pure functions of the ground and a shape (F6). They run again on the ground
  after each commit. Treasure and loot may call the same functions (F7).
- Promise check: a pure function of a finished map and its homes (F5). The same function
  reads corpus maps.
- Snug fit: a pure function with one rule per size class, chosen by the body's size (F6,
  F8). Siting asks for snug spots first and any spot second, through the same fit.
- Zone record: a lookup from a tile to its zone (F9).

**Claims.**

- C1 to C7: re-derived from the problem. They are the promise itself.
- C8, C10: re-derived from F1. A per-zone count cannot see a player's reach.
- C9: re-derived from F4.
- C11, C12: re-derived from the problem's fairness and F3.
- C13: re-derived. Large and rare objects have the fewest spots, so they choose first.
- C14: re-derived from the problem: a short map is better than a failed run.
- C15, C16: re-derived from the corpus look. Vegetation overlaps 80% of corpus sprites.
- C17: rejected by C29. One score cannot say what fits a one-tile object and a castle.
  Cover stays as a tiebreak.
- C18: re-derived from the corpus flank share.
- C19: rejected by C30.
- C20: kept as a rule, rejected as a stored value. Revised, see R1.
- C21: re-derived. Seals keep a mine's front guard from being walked around.
- C22, C23: re-derived from the road contact measure.
- C24: re-derived from F5.
- C25: kept for now. See A7.
- C26: rejected by C8 and C10.
- C27: rejected. The map-wide quota already counts the corpus rate of mines. See A6.
- C28: kept. See R3.
- C29: re-derived from F8 and the corpus snug share. See A11.
- C30: re-derived. The front guard needs no second variant.

**SOLID check.**

- Single responsibility: every Owns reads without "and".
- Open/closed: a fourth size class adds one rule in Snug fit and changes nothing else.
- Liskov: no concept has variants. The snug spots are a filter over the same fit, not a
  second kind of fit.
- Interface segregation: Snug fit takes a shape, an anchor and a closed test only.
- Dependency inversion: Siting asks whether a spot is snug and never knows the size rules.

**Open lookups.**

- L1. Do treasure and loot read the map after gameplay, or a stored pool? Decides whether
  C20 needs a value.
- L2. Do downstream steps read gameplay results per zone? Decides whether Zone record is
  needed.
- L3. Can a body straddle two zones today? Decides whether Standing can reuse a per-zone
  commit.
- L4. Does the effort reading price one home or the nearest of many? Decides Reach.
- L5. What guard levels do mines carry today? Decides Guard post.

## 5. Mapping onto the existing system

**Revision log.**

- R1. Section 2, Spot survey: the spot pool is no stored value. L1 found that loot finds
  its pockets from the occupied tiles after gameplay (`core/steps/loot/step.py:30`).
  "Gameplay first" holds by order alone.
- R2. Section 2, Standing: Zone record added. L2 found gated, scatter and portal read
  `GameplayResult` per zone (`gated/step.py:80`, `scatter/step.py:48`,
  `portal/step.py:101`).
- R3. Section 2, Standing: Town tie added. The design missed it. `tie_dwellings` links a
  random dwelling to its zone's town (`gameplay/economy.py:50`).
- R4. Section 2, Guard post: the level rule changes. Today a mine's guard level comes from
  one table by resource: rare mines 4 or 5, gold 6 (`placement/site.py:61`). C3 sets a
  guaranteed rare copy to 3.
- R5. Section 2, Reach: Home groups visit tiles by player. L4 found `effort_map` prices
  from the nearest of all homes (`reading/effort.py`), and `homes` returns visit tiles of
  every town in one list (`planning/pricing.py:54`).
- R6. Section 2, Allocation: Identity pick added. The design missed two things. A mine's
  sprite carries a terrain apron, so its variant follows the spot's terrain
  (`gameplay/economy.py:27`). A failed fit falls back to a smaller object of the same
  purpose (`gameplay/fallback.py`).
- R7. Section 2: Shortfall tally moved from Allocation to Accounting. Allocation had eight
  concepts, and only Accounting sees the finished whole.
- R8. Section 2, Allocation: Held reach added, and fairness counts what each player reaches,
  not who arrives first. A tile belongs to the player who reaches it first, and one player
  reaches two to four times more land first on most seeds. Equal counts by first arrival
  were out of reach. A player reaches an object in band b and in every band after it, so
  Held reach counts cumulatively. Siting ranks a spot by how far it would spread those
  counts before it ranks by band.
- R9. Section 3, invariant 6: the bound holds while placing, not on the finished map. A
  later object can lengthen the path to an earlier one and push it across a band edge. On
  twenty maps, eight end with one to three families two apart, always in the nearest two
  bands. The finished-map check allows two. Siting prices the map again after every 12
  objects, which removes two of those ten. Siting also ranks a spot by the worst tier
  within 3 tiles, because an object slides up to 3 tiles from its centre and could
  otherwise cross into a worse tier.
- R10. Section 3, invariant 3: the promise check counts the mine's own guard. A gold mine
  carries a level 6 guard, 28 days of toll, so no gold mine stands inside 14 days. Ten seeds
  measured 29 to 49 days. Band plan needs no floor of its own for gold.
- R11. Section 6, slice 3: generated travel runs shorter than the corpus. Each family's
  median sits inside the corpus p10 to p90, and below the corpus median for most families.
  The corpus maps are larger and more cut up. Terrain owns that gap, and this note leaves it
  out of scope.
- R12. Section 3, invariant 6: the zone plan's sea objects count as standing. Buoys and
  mermaids stand on water before the pass, and one markov map gave the sea's player three
  more shrines near home. Siting ranks a spot by how much it changes the spread, so a spot
  that narrows a gap the sea opened ranks below zero and stands.
- R13. Section 2, Spot survey and Standing: Pocket and Mouth guard are gone, and Snug fit
  replaces the one-formula cover score as the first test of a spot. The user set the rule
  by size, C29 and C30. Before the change, 22% of generated one-tile objects sat in a hole
  or a corner against 81% on the corpus. Cover stays as a tiebreak. F8 and slice 4
  changed with it.

**Parts.**

| Part | Verdict | Where |
|---|---|---|
| Targets | Reshape | `corpus/mine/effort.py` reads effort at artifact pickups only. It gains a per-family reading. |
| Reach | Exists, revised R5 | `core/reading/effort.py`, `core/reading/routes.py`, `core/planning/pricing.py` |
| Spot survey | Reshape | `core/placement/site.py` fits per zone. A new `core/placement/spots.py` holds the map-wide survey. |
| Allocation | New | `core/steps/gameplay/`: `allocate.py` keeps the promise, `placer.py` runs the map-wide pass. They replace the zone draw. |
| Standing | Exists, mismatch | `ZoneSite.commit` (`placement/site.py:431`) |
| Road courtesy | Reshape | `core/steps/roads/network.py:93` |
| Accounting | New | `core/reading/promise.py` |

**Concepts.**

| Concept | Verdict | Where, and the mismatch |
|---|---|---|
| Home effort reading | New | Beside `pickup_efforts` (`corpus/mine/effort.py:46`), reusing its owners and routes |
| Target band | New | A new table in `data/pp/effort.json`, loaded by `corpus/effort.py` |
| Density | Reshape | Per-terrain densities exist (`placement/intensity.py`). `gameplay/quota.py` sums them over the sites. |
| Flank share | New | `core/reading/`, so corpus and generated maps read the same way |
| Home | Reshape, R5 | `planning/pricing.py:54` |
| Toll | Exists | `priors/effort.py:73` |
| Reach field | Exists | `reading/effort.py` `effort_map`, called once per home |
| Shape | Reshape | `placement/guards.py` `fits` checks body and gap. The front tile check is mine-only (`site.py:315`). |
| Ground | Exists | `LevelField` (`site.py:150`) |
| Spot | New | `core/placement/spots.py` |
| Cover | Reshape | `back_score` (`site.py:77`) scores the back only |
| Snug fit | New, R13 | `grid/snug.py` holds the rule, `reading/snug.py` reads it on any map, `SnugFooting` in `placement/site.py` keeps the snug anchors |
| Promise list | Reshape | `Ledger` (`economy.py:19`) tracks missing resources map-wide, not per player |
| Quota | Reshape | `gameplay/quota.py`. It replaces the per-zone count of the zone draw. |
| Band plan | New | `gameplay/bands.py` |
| Held reach | New, R8 | `gameplay/reach.py` |
| Order | New | `gameplay/bands.py` `slot_order` |
| Siting | Reshape | `gameplay/siting.py` ranks the tiles map-wide. `ZoneSite.place` (`site.py:381`) still walks a 7 by 7 window around each centre. |
| Identity pick | Exists, R6 | `mine_variants`, `smaller`, `gameplay/pick.py` |
| Repair | New | `allocate.py` |
| Claim | Exists | `LevelField.claim` (`site.py:193`), `MapState.accepts` |
| Guard post | Reshape, R4 | `_guarded_front` (`site.py:455`) |
| Seal | Exists | `site.py:497` |
| Flank filler | New | `core/placement/` |
| Reach keeper | Exists | `reach_without` (`site.py:336`) |
| Zone record | Exists, R2 | `PlacedZone` (`site.py:518`) |
| Town tie | Exists, R3 | `economy.py:50` |
| Served objects | Exists | `sites_of` (`roads/sites.py:58`) |
| Courtesy price | New | `step_cost` (`roads/network.py:93`) prices terrain only. Roads already avoid blocking cells but cross overlay and entrance tiles. |
| Promise check | New | `core/reading/promise.py` |
| Shortfall tally | Reshape | Scattered prints today (`gameplay/step.py:222`) |

**Mismatch: Standing is bound to a zone.** A `ZoneSite` owns one zone's tiles, reach and
objects (`site.py:257`). The design's Standing knows no zone. The code is wrong for this
problem, but L3 found a body never straddles two zones (`ZoneFooting`, `site.py:555`).
The design keeps the zone sites as the commit path: Siting picks a spot map-wide, and the
zone site that owns the spot's tiles stands the object (A3). This keeps per-zone results
for gated, scatter and portal at no cost.

**What the existing system has that the design lacks.**

- The per-zone reward scale (`gameplay/step.py:343`). Waste for gameplay, per C10.
  Treasure and loot keep it.
- The intensity heat map per purpose (`site.py:363`). Waste. Band and cover replace it.
- The economy pair pulled next to the town (`gameplay/step.py:84`). Waste. The promise
  covers wood and ore.
- The neutral town's two extra mines (`draw.py:100`). Waste, per C27 and A6.
- Accent landmarks and the dragon dwelling on their patches (`gameplay/step.py:214`). A
  concept the design covers: a landmark's spot is its patch, and it counts against its
  family's quota.
- The town and shipyard placers. Outside this design, per C8.

**Claims against the code.**

- C1, C2, C4, C6, C7: the code does not follow them. The design does.
- C3: the code guards rare mines at 4 or 5. The design follows C3.
- C5: the code drops a mine with a warning. The design follows C5.
- C8 to C14: the code places per zone. The design follows the claims.
- C15 to C18: the code scores the back only. The design follows the claims.
- C19: loot guards pocket mouths. Gameplay does not. The design rejects C19, per C30.
- C29: the code scored back and flanks in one sum. The design follows C29.
- C30: both follow it.
- C20: the code follows it by order. The design keeps that, R1.
- C21: both follow it.
- C22, C23: the code crosses overlays freely. The design follows the claims.
- C24: the sweep checks finishing only (`seed_sweep_test.py`). The design adds the promise.
- C25: both follow it. See A7.
- C26, C27: the code follows them. The design rejects them.
- C28: both follow it.

## 6. Slices

The loop listed the miner first. The first slice here is the promise instead, because it is
the thinnest path a player can see. The miner comes when bands need targets.

1. **Every player gets the six mines.** Reach per home, Promise list, Siting over the
   existing zone fits, Guard post level rule, Repair, Promise check. Mines leave the zone
   draw. Other objects stay per zone. Done when: the promise test passes on one seed in
   `make test` and on ten seeds in `make sweep`, both terrain models, two players.
   `make golden` is regenerated.
2. **Objects sit snug.** Shape, Spot, Cover, Flank share, Flank filler. Siting ranks spots
   by cover. Done when: the closed-flank share on ten seeds sits within the corpus spread,
   about 2 in 3. The promise still holds.
3. **One map-wide count, fair bands.** Home effort reading, Target band, Density, Quota,
   Band plan, Held reach, Order, Identity pick, Shortfall tally. The zone draw is gone.
   Done when: per family, the generated median effort sits within the corpus p10 to p90.
   Per band, the objects of a family each player reaches differ by at most one while
   placing and at most two on the finished map (R9). Total density is within 10% of the
   corpus rate. The promise holds.
4. **Snug fit by size.** Snug fit, Siting. Revised, see R13. Siting tries the drawn object
   on snug spots first, then on any spot, then gives way to a smaller one. Done when: on
   nine seeds in ten of each terrain model, each size class with at least 8 objects
   reaches the corpus p10 snug share (A11). The hemmed share stays within 10 points of
   the corpus share on nine levels in ten. The promise holds.
5. **Roads keep off.** Served objects, Courtesy price. Done when: road contact with
   unserved objects is at most 6% on ten seeds. Measured: 4.8% on ten seeds at size 72,
   down from 5.3%, against 6.5% on hand-made maps. The rest sits on the top rows of
   sprites, which a hero walks under.

Each slice passes `make check`, updates the docs it renames, and is committed on main.

## 7. Assumptions

1. **Assumption:** a spot within 14 days exists for each basic resource for each player on
   a 72-tile map. **Decided:** the fallback past 14 days is a warning in a run and a failure
   in the test seeds. **Basis:** the user: "there is always some space somewhere". Generated
   maps leave empty nooks today. **If wrong:** Repair, slice 1's done-when, invariant 1.
2. **Assumption:** steps after gameplay do not lengthen a route to a guaranteed mine past 14
   days. **Decided:** the promise check runs on the finished map and fails the test seeds.
   Among spots inside 14 days, Siting prefers the lower effort. **Basis:** cut-off places
   are unreached at gameplay time, so gated guards stand off the walking routes
   (`planning/pricing.py`, `Opener`). Treasure and loot guards could still stand on a route.
   **If wrong:** invariant 1 gains a protected-route set that later steps consult.
3. **Assumption:** an object's body lies inside one zone. **Decided:** Standing reuses the
   zone sites. **Basis:** `ZoneFooting` (`site.py:555`). **If wrong:** Standing becomes a
   level-wide site, and Zone record reads the visit tile.
4. **Assumption:** pricing the map three times per run is cheap enough. **Decided:** no
   re-pricing per commit. **Basis:** measured 0.25 s at 72 and 1.16 s at 144 for 4 homes.
   **If wrong:** F2, and the flow's pricing moments.
5. **Assumption:** the corpus marks player homes well enough to read effort from them.
   **Decided:** Home effort reading reuses the owners the effort miner already reads.
   **Basis:** `pickup_efforts` reads owners (`corpus/mine/effort.py:46`). **If wrong:**
   Targets, slice 3.
6. **Assumption:** a neutral town needs no mines of its own. **Decided:** C27 is rejected.
   **Basis:** the map-wide quota counts mines at the corpus rate, C9. **If wrong:** Quota.
7. **Assumption:** bodies keep 2 tiles apart, as today. **Decided:** Ground keeps the gap.
   **Basis:** none. Hole fill may want objects closer. Slice 2 measures the nearest-body
   distance on the corpus. **If wrong:** Ground, Cover.
8. **Assumption:** a mine underground counts for the promise when a gate leads to it.
   **Decided:** Reach prices both levels. **Basis:** `route_map` pairs the underground ends
   of gates (`reading/routes.py:80`). **If wrong:** Reach, Promise check.
9. **Assumption:** the test seeds run at size 72 with the default two players. **Decided:**
   slice 1's test uses that setup. **Basis:** the CLI default is two players
   (`cli/steps.py:83`). **If wrong:** the promise may break with more players on small maps.
   Slice 1 adds a four-player seed to the sweep.
10. **Assumption:** the uncommitted work in the tree belongs in its own commit before slice
    1. **Decided:** no slice commits until the tree is clean. **Basis:** 52 modified files
    and several new modules overlap the files the slices change. `make check` passes on
    them. **If wrong:** slice commits mix in unrelated work.
11. **Assumption:** the corpus p10 per map is the right floor for the snug share.
    **Decided:** the floor is 61% for one tile, 58% for two and 82% for three or more.
    **Basis:** pooled over the corpus, 81% of one-tile objects, 74% of two-tile objects and
    92% of larger ones sit snug. Nine maps in ten reach the floor, so the sweep asks the
    same of nine generated maps in ten. One map in ten with forest holes under tree tops
    falls short, as hand-made maps do. **If wrong:** slice 4's done-when, Snug fit.
