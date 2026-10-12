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
- Over the first 40 hero-days, every player claims about as much value as the best player.
  A player claims an object when no other player reaches it sooner. At 20 and at 40 days,
  the worst player's claimed value is at least 0.8 of the best player's (A15). Today a
  six-player 144 map gives the worst player 16% of the best at 10 days and 42% at 20.
- An object's guard looks like a hand-made map's guard for that kind of object. Most
  objects stand unguarded or behind a level 1 to 4 monster, as 91% do on the corpus.
  Dwellings of levels 5 to 7, Dragon Utopia and gold mines take the strong guards. No
  gameplay object stands behind a neutral dragon of levels 8 to 10. Today a six-player 144
  map guards 94% of its objects at a mean level of 5.4, and an object within 3 days of a
  home averages level 7 against 1.6 on the corpus.

**Out of scope.**

- How much walkable ground vegetation leaves.
- The guard's growth with travel days. The corpus adds about one level from 3 to 10 days
  (A14).
- Guards in front of artifacts and of cut-off prizes. They keep the effort reward rules.
- Carved underground gate sites.
- Treasure, loot, sets and quests. They keep their own placers and see the map after
  gameplay placement.

## 1b. Claims

Source for C1 to C24: the settled grill, 2026-10-05. Source for C25 to C28: the existing
code. Source for C29 and C30: the user, 2026-10-05, after slice 3. Source for C32 to C34:
the user, 2026-10-12, after the guard study of R18.

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
28. A random dwelling takes the faction of the town, neutral or not, a hero reaches it
    from in the fewest days.
29. A spot fits by the object's size. A one-tile object fits any hole, any corner and any
    L-shaped corner. A two-tile object fits left or right of vegetation, with the vegetation
    on the side away from its visit tile. A larger object fits with its top against
    vegetation, or in an open field.
30. There are no pockets and no mouth guards. Only mines carry a guard, in front. Mines are
    three tiles, so they never need a nook. Every object stays reachable, so its guard can
    stand in front.
31. A spot that would give some players more of a family than others still takes the
    object. A stronger guard in front rebalances the odds. Source: the user, 2026-10-05,
    after four-player maps came up short. Revised by C32 and C33.
32. Fairness is the placer's job over the first 40 hero-days. Each player's value claimed
    within 5, 10, 20 and 40 days should come close to the best player's.
33. Each family draws its guard from its own corpus record: whether it is guarded, and at
    which level. There are no target days, no band top-up and no equation.
34. Levels 8 to 10 never guard a gameplay family. Most families end up unguarded or at
    level 1 to 4, because most objects are worth little. A dragon suits a prize like the
    Armageddon's Blade, and that prize is out of scope here.

## 2. Parts and concepts

### Level 1: parts

1. **Targets.** What hand-made maps teach about where objects stand. It owns, per object
   family, how far from home the corpus puts it, how many stand per walkable tile, how
   often an object's flanks are closed, and how hand-made maps guard it. It never knows a generated map. It hands its tables
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
   check, the claimed value check and the shortfall tally. It never knows how objects were
   placed.

**Flow.**

- Before any generation, Targets reads the corpus once and stores its tables.
- When player towns, gates and shipyards stand, Reach prices the map from each home.
- Allocation lists the objects. It takes the guaranteed mines first. For each object it asks
  Spot survey for spots, filters them by the effort band the target wants, and picks one.
  Standing puts the object on the map, and Spot survey reads the changed ground for the
  next object.
- After the guaranteed mines, Reach prices the map again. Accounting checks the promise.
  Allocation repairs a broken promise by adding or swapping a mine.
- After all gameplay objects stand, Accounting checks the promise again, checks each
  player's claimed value and tallies the shortfall.
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
| Guard record | Per family, the corpus share guarded and the spread of guard levels | Spots |

Guard record was added. See R18.

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
| Held value | Per player, the value it claims within 5, 10, 20 and 40 days | Families |
| Order | Which object goes next | Bands |
| Siting | The one spot an object takes, by even claimed value, then band, then spread, then cover | How spots are found |
| Identity pick | Which object of a family stands on a spot, by its terrain and its size | Effort |
| Repair | The mine to add or swap when the promise breaks | Spot scoring |

Identity pick was added. See R6. Held reach was added in R8 and became Held value in R19.
Fair guard was added in R14 and removed in R18.

**Standing**

| Concept | Owns | Never knows |
|---|---|---|
| Claim | The cells an object takes | Why it stands there |
| Guard post | Where an object's guard stands | Spot scoring |
| Guard draw | Whether an object is guarded and at which level, from its family's record | Spots |
| Seal | The blocking decorations beside a mine's entrance | The guard |
| Flank filler | A decoration matching the terrain on an open flank | Families |
| Reach keeper | Refusing a commit that strands walkable ground | Families |
| Zone record | The zone each placed object reports to | Allocation |
| Town tie | The town a random dwelling takes its faction from | Spots |

Zone record and Town tie were added. See R2 and R3. Guard draw was added. See R18.

Guard post stands a guard on the tile in front of an object's entrance, at the level Guard
draw chose. It has one way to do it. Revised, see R13, R14 and R18. Guard draw runs before
Siting, so Siting prices each spot with the guard the object will have.

**Road courtesy**

| Concept | Owns | Never knows |
|---|---|---|
| Served objects | The objects a road leads to | Prices |
| Courtesy price | The extra price of a step on the sprite or entrance of an object not served | Families |

**Accounting**

| Concept | Owns | Never knows |
|---|---|---|
| Promise check | Per player and basic resource, the nearest mine's effort and the gap between players | Repair |
| Value check | Per player, the value claimed within 5, 10, 20 and 40 days against the best player's | Siting |
| Shortfall tally | Per family, the quota against the count placed | Spots |

Shortfall tally moved here from Allocation. See R7.

## 3. Invariants

1. Every player reaches a mine of each basic resource within 14 hero-days. **Owner:**
   Promise check. Upheld by Promise list, Repair and Reach keeper.
2. For each basic resource, the gap between players is at most 3 days. **Owner:** Promise
   check. Upheld by Promise list.
3. No gold mine stands within 14 days of any player, its own guard counted. **Owner:**
   Promise check. Upheld by Siting, which counts the guard Guard draw gave the mine. See
   R10 and R18.
4. No body covers another body, the vegetation web, or another object's entrance or front
   tile. **Owner:** Claim. Upheld by Ground and Shape.
5. Every tile a hero could walk before a commit stays reachable after it. The open tiles
   beside a new body or a flank decoration that joined through its tiles still join
   within two tiles of it. **Owner:** Reach keeper. Upheld by Seal and Flank filler, which
   ask it first. See R17.
6. At 20 and at 40 hero-days, the worst player's claimed value is at least 0.8 of the best
   player's on the finished map. An object counts at its effort with its own guard, since
   the claimer must beat it. **Owner:** Value check. Upheld by Siting through Held value.
   Revised, see R19. The former rule, even counts per family and band, held through R8, R9,
   R14 and R16. Superseded by `compensation.md`: the placer no longer weighs players, and a
   player below the corpus median share gets an artifact prize after placement.
7. The map never holds more objects of a family than its quota. **Owner:** Quota. Upheld by
   Siting.
8. A road crosses an object it does not serve only where no other way exists. **Owner:**
   Courtesy price.
9. No gameplay object stands behind a guard of level 8 to 10, or behind a level its
   family's record never shows. **Owner:** Guard draw. See R18.

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
- F10. Four players on a 72-tile map share most of the near ground. Most tiles fall in band
  1 for two or three players at once, so one more object there gives those players more
  than the rest. On seed 25 every slot that failed had 22 to 325 legal spots, and none to
  seven of them kept the players even.
- F11. Siting ranks every site tile for every object. On seed 25 with four players the
  ranking takes 40 s of the 96 s gameplay pass. Ranking once per guard level multiplies
  that.
- F12. Fairness and a guard's size change for different reasons. A guard follows what
  hand-made maps put in front of that kind of object. Fairness follows where each player's
  hero gets first. A guard buys little fairness: it adds the same toll for every player,
  and the study of R18 found the band guards left the worst six-player map at 16% of the
  best player's value at 10 days.
- F13. Value counts, not the number of objects. A shrine and a level 7 dwelling are one
  object each, and a player who gets the dwelling holds far more.

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
- Guard record: a plain table keyed by family, mined from the corpus (F3, F12). No
  per-family code.
- Guard draw: a plain function of the record and the seeded draw (F12). It replaces the
  ranking per guard level, so Siting ranks each tile once (F11).
- Held value and Value check: one pure function over a table of objects by players, in
  days and value (F13). Siting asks it how a spot would change the worst player's share. A
  test feeds it a hand-made table without a map.

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
- C30: re-derived. The front guard needs no second variant. Revised by C31: a fair guard
  stands in the same front, so the front still has one variant.
- C31: rejected by F12. A guard sets the same floor on the toll for every player, but the
  study of R18 found it buys little fairness and makes near objects cost more than
  hand-made maps make them.
- C32: re-derived from F10 and F13. The placer is the only part that decides who gets
  first to what.
- C33, C34: re-derived from F12. No corpus gameplay family uses level 8 to 10.

**SOLID check.**

- Single responsibility: every Owns reads without "and".
- Open/closed: a fourth size class adds one rule in Snug fit and changes nothing else.
- Liskov: no concept has variants. The snug spots are a filter over the same fit, not a
  second kind of fit.
- Interface segregation: Snug fit takes a shape, an anchor and a closed test only.
- Dependency inversion: Siting asks whether a spot is snug and never knows the size rules.
  Siting takes the guard Guard draw gives it and never knows the record.

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
  purpose (`placement/fallback.py`).
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
- R14. Section 2, Allocation: Fair guard added, and Siting stands an object on a spot that
  would spread the players when a guard in front evens them out. The user set the rule,
  C31. On seed 25 with four players the map came up 30 objects short while hundreds of
  legal spots stood empty (F10). A guard's toll counts for every player, so Held reach
  counts the object at its effort plus that toll. Band plan keeps the effort without the
  guard, as Home effort reading does on the corpus. Siting ranks by even reach, then by
  the weakest guard, then by player, band and target. Invariant 6, F10, F11 and slice 6
  changed with it.
- R15. Section 3, invariant 6: a spot that narrows a gap stands. Slice 4 kept only spots
  that change the spread by exactly zero, and so dropped the spots R12 ranks first.
  Siting keeps every spot that does not widen the spread.
- R16. Section 3, invariant 6: an object counts at its effort past its own guard, not at
  its effort plus the guard's toll. A hero pays the toll of the strongest guard on the
  way, so a fair guard no stronger than one the route already beats costs nothing more.
  The ten-seed sweep found the two rules apart: Siting added the toll, the sweep measured
  without the guard, and eleven seeds read a gap of 3 to 6. Siting and the sweep now count
  every object but a mine or a town past its own guard, a landmark's included.
- R17. Section 3, invariant 5: a body may not send a hero the long way round. The sweep
  read seed 7 with a gap of 3. Three level 2 dwellings stood within 4 days of both
  players, and a later dwelling closed the corridor to two of them. The loop round it
  raised one player's trip to 10 days. Reach keeper refused only a cut that split an
  area, and a loop kept the area whole. It now also refuses a body or a flank decoration
  whose open neighbours no longer join within two tiles of it. A seal still closes a
  front, since a guard's front must cut.
- R18. Section 2, Targets and Standing: Guard record and Guard draw added, Fair guard
  removed. A study read every corpus mine and gameplay object with all guards in place,
  25,542 objects on 159 maps, and the same on generated maps at 72 and 144. On the corpus,
  91% of these objects stand unguarded or behind level 1 to 4. Level 5 or more guards
  9.3% of them, mostly dwellings of levels 5 to 7 (45% to 75% of them), the golem factory
  and the earth conflux (about 50%), the cartographer (40%), Dragon Utopia (34%) and gold
  mines (30%). No corpus gameplay family stands behind level 8 to 10. The guarded share
  runs from about 40% for sawmills, ore pits and banks to 91% for rare mines and 94% for
  gold. Generated 144 maps guard 94% of their objects at a mean level of 5.4, and about
  40% at level 7 or more. Generated 72 maps guard 69% at a mean of 3.7. The cause is the
  band rule: an object of no player took the guard that lifts its effort to its target
  band, so the guard paid the target days minus the travel, and the nearest objects took
  the biggest guards. Objects within 3 days of a home average level 7.0 against 1.6 on the
  corpus. Travel matches the corpus, a median of 5 days and a p90 of 10. F12, C31 to C34,
  invariants 3 and 9, and slices 6 and 7 changed with it.
- R19. Section 2, Allocation: Held value replaces Held reach, and fairness counts value
  claimed first over the first 40 hero-days. A player claims an object when no other
  player reaches it sooner, guards included. R8 dropped first arrival because equal counts
  by first arrival were out of reach. Value over a 40-day horizon asks less: the measure
  sums across families, and it stops before the far land one player may hold alone. The
  study of R18 read the worst player's share of the best player's value: generated 144
  maps give 16% at 10 days and 42% at 20, generated 72 maps 41% and 89%. Corpus 72 maps
  give 51% and 89%, and corpus 144 maps 25% and 27%. The corpus is no fairness reference,
  since many of its large maps are scenarios. Invariant 6, F13, Value check and slice 8
  changed with it.
- R20. Section 7, A12 and A13: superseded by R18. No fair guard remains, so its cap and
  its band rank fall away.
- R21. Section 7, A17: a guaranteed mine draws its guard from its family's record, capped
  at the C3 level, and the promise prices it at the drawn level. When a player still stays
  behind, the promise steps the level down to no guard. A wood, ore or rare mine of the
  map-wide pass takes the lowest level from its draw up to its promised level that keeps
  the players even on its resource. Slice 7 found the cause: one player got an unguarded
  rare mine a day from home and another got none, which opened a 10-day gap on the
  promise.
- R22. Section 6, slice 7: the guarded share compares the guard at an object's door. The
  record keeps the strongest guard beside a door, while the study of R18 counted every
  guard on the cheapest route, the territory gates among them. Banks read 5% guarded at
  their door on the corpus and 41% on the route. The gates step decides the route share:
  a gate closes 5% to 74% of objects at 144 by seed, against 25% on the corpus. Siting
  also stopped filtering out every tile that widens the gap between players. It ranks
  them last instead, because without the fair guard only a quarter of the land passed the
  filter and seeds 5 and 7 at 72 stood short.

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
| Guard record | New, R18 | A miner in `corpus/mine/` beside the family efforts, a table in `data/pp/`, loaded by `core/priors/` |
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
| Held value | Reshape, R19 | `gameplay/reach.py` counts objects per family and band. It counts value per player over the day marks instead. |
| Order | New | `gameplay/bands.py` `slot_order` |
| Siting | Reshape | `gameplay/siting.py` ranks the tiles map-wide. `ZoneSite.place` (`site.py:381`) still walks a 7 by 7 window around each centre. It ranks every tile under every guard level through `fair_guard`, and `_lifted` picks the guard that lifts a tile to its band (R18). Both go. |
| Identity pick | Exists, R6 | `mine_variants`, `smaller`, `gameplay/pick.py` |
| Repair | New | `allocate.py` |
| Claim | Exists | `LevelField.claim` (`site.py:193`), `MapState.accepts` |
| Guard post | Reshape, R4 | `_guarded_front` (`site.py:552`) |
| Guard draw | New, R18 | `core/placement/`, beside the guard placement code. It replaces `gameplay/fair_guard.py`. |
| Seal | Exists | `site.py:497` |
| Flank filler | New | `core/placement/` |
| Reach keeper | Exists | `reach_without` (`site.py:336`) |
| Zone record | Exists, R2 | `PlacedZone` (`site.py:518`) |
| Town tie | Exists, R3 | `economy.py:50` |
| Served objects | Exists | `sites_of` (`roads/sites.py:58`) |
| Courtesy price | New | `step_cost` (`roads/network.py:93`) prices terrain only. Roads already avoid blocking cells but cross overlay and entrance tiles. |
| Promise check | New | `core/reading/promise.py` |
| Value check | New, R19 | `core/reading/`, so the sweep reads corpus and generated maps the same way |
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
- C31: the code follows it through the fair guard. The design rejects it, R18.
- C32: the code keeps per-family counts even by band. The design follows C32, R19.
- C33, C34: the code draws the guard from the band and tries every level up to 10. The
  design follows the claims, R18.

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

6. **Fair guards.** Fair guard, Held reach, Siting, Guard post. Siting first takes the
   spots that keep the players even unguarded, then the spots a guard of level 1 to 4
   evens out. Done when: seed 25 at size 72 with four players places at least 90% of its
   quota, from 85% today. The ranking costs no more time than today's. The two-player
   sweep still passes. Measured: 160 of 161 objects, 99%, with 29 behind a fair guard.
   The gameplay pass takes 69 s, down from 96 s. One neutral town still finds no fair
   spot, since towns take no fair guard. Superseded by slices 7 and 8, R18 and R19.
7. **Guards from the corpus record.** Guard record, Guard draw, Guard post, Siting. Each
   object draws its guard before Siting, and Siting ranks each tile once. The fair guard and
   the lifting guard go. Done when: on seeds 1 to 4 at 72 with four players and seeds 1 to 3
   at 144 with six players, each family's guarded share sits within 10 points of its corpus
   share. Level 5 or more guards between 5% and 15% of gameplay objects. No gameplay
   object stands behind level 8 to 10. Objects within 3 days of a home average level 3 or
   less. The promise and the gold rule still hold, and `make check` and `make sweep` pass.
   The value check prints its shares beside the corpus, with no bar yet.
   Measured (R22): the guard at an object's own door follows the corpus record. On those
   seeds, 2.2% of gameplay objects at 72 and 2.3% at 144 stand behind level 5 or more at
   their door, against 2.1% the record gives for the same mix. No object stands behind
   level 8 to 10. Objects within 3 days of a home average level 0.9 at 72 and 0.8 at 144,
   counting every guard on the route. Each family with at least 20 objects sits within 10
   points of its door record, except ore pits at 144 (43% against 31%) and the level 1
   dwellings at 144 (60% against 35%). Counting every guard on the route, level 5 or more
   guards 4.5% at 72 and 6.2% at 144, and banks read 16% guarded at 72 against 41% on the
   corpus. That gap is the gates, not the draw. Every map of the sweep stands its full
   plan bar the magic wells of seed 7 at 72, 0 of 5, for lack of open room. With four
   players at 72, the promise breaks 8 times on seeds 1 to 4, each gap at most 11 days and
   no player past 14 days, against 11 breaks and up to 31 days before.
8. **Fairness by placement over 40 days.** Held value, Siting, Value check. Siting ranks a
   spot first by how it moves the worst player's share of claimed value. Done when: on the
   same seeds, the worst player's share is at least 0.8 of the best player's at 20 and at
   40 days (A15). The map places at least 95% of its quota. The gameplay pass takes no
   longer than today's. Dropped: `compensation.md` replaces this slice with a prize for each
   player behind the bar.

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
12. **Assumption:** a fair guard stops at level 4, 12 days of toll. **Decided:** Fair
    guard tries levels 1 to 4 and no higher. **Basis:** 12 days moves any band-1 object past
    the 8-day band edge for every player. A level 5 guard costs 18 days, which puts a
    temporary bonus behind a monster no player would fight for it. **If wrong:** Fair guard,
    slice 6's done-when. **Revised 2026-10-11:** the fair guard tries every level up to the
    toll's top, 10, because a guard's job is to slow the player it favours and no toll is
    too high for that. The bands past the corpus keep a strong guard's object in a band the
    players who reach it count alike. **Superseded 2026-10-12:** no fair guard remains.
    Each family draws its guard from its corpus record, see R18 and R20.
13. **Assumption:** the corpus measures an object's effort without its own guard, so the
    fair guard leaves the object's band in Band plan alone. **Decided:** Siting ranks band
    and target by the effort without the guard, and Held reach counts it past the guard.
    **Basis:** Home effort reading strips the guards beside an object's doors on the corpus
    and on generated maps alike. **If wrong:** Siting's band rank, Target band.
    **Superseded 2026-10-12** with A12, see R20. Siting still ranks band and target by the
    effort without the object's own guard, so Target band keeps its corpus reading.
14. **Assumption:** a family's guard can ignore travel days. **Decided:** Guard draw takes
    the family's pooled record, with no distance term. **Basis:** on the corpus, a guard's
    level grows about 1.5 times the log of one plus the nearest player's days, R² 0.25.
    That is about one level from 3 to 10 days, and corpus travel sits at a median of 3
    days and a p90 of 8. The gap between the two nearest players adds nothing once the
    distance is known (slope -0.05). The user chose the simpler rule. **If wrong:** Guard
    record gains a level spread per day bin, if maps read flat.
15. **Assumption:** a 0.8 share at 20 and 40 days is a fair map and a reachable bar.
    **Decided:** invariant 6 and slice 8 use 0.8 at 20 and 40 days. The 5 and 10 day marks
    are printed with no bar. **Basis:** generated and corpus 72 maps both reach 0.89 at 20
    days. The 5 and 10 day marks hold a handful of objects per player, so one object swings
    the share. **If wrong:** invariant 6, slice 8's done-when. Superseded: the corpus 72
    maps read a median share of 0.46 at 20 days and 0.38 at 40, and `compensation.md`
    takes those medians as its bar.
16. **Assumption:** an object's worth is its value reading, in gold. **Decided:** Held value
    sums the value reading the effort reward already uses. **Basis:** the study of R18 read
    claimed value that way. **If wrong:** Held value, Value check.
17. **Assumption:** placement alone can even out the towns and the guaranteed mines, which
    stand by their own rules. **Decided:** towns and guaranteed mines count in Held value,
    and the objects after them close the gap. Guaranteed mines draw from their record but
    never above the guard C3 sets, since a drawn level 6 on a promised mine would break
    the 14-day promise (R21). **Basis:** the
    C3 levels match the corpus near home: rare mines read level 2.5 and sawmills and ore
    pits 1.3 at 3 days. A town's share of claimed value is not measured. **If wrong:**
    neutral towns take a guard by fairness again, as neutral-town-spacing.md first set.
