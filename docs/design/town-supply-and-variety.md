# Town supply and object variety

Disclosure: before this note I had read the gameplay placement code, the promise allocator,
the kind picker, the band plan, the landmarks and the quota, while measuring seed 25 at size
144. The decisions they carry are listed as claims in 1b.

## 1. Problem

A player who takes a neutral town on a large generated map often finds no sawmill and no ore
pit near it, so the town cannot build without a long trip for wood and ore. Walking out from
home, the same player meets a second gem pond or crystal cavern before their first sulfur
dune. A gold mine sits a few steps from some homes, so one player starts rich and no rival
can contest it. The player also walks past three or four copies of one visitable, such as
four universities, inside one small region.

Measured on seed 25 at size 144, 4 players, two levels, no water:

- Player towns have a sawmill and an ore pit within 5 to 11 tiles.
- Neutral towns sit a median 16 tiles from a sawmill and 18 from an ore pit. One in ten sits
  79 tiles or more from one.
- The map holds 24 towns, 14 sawmills and 13 ore pits.
- The player at (12,69) meets the rare mines in this order, nearest first: mercury 11,
  gems 14, crystal 20, gems 20, mercury 24, sulfur 24. The player at (141,66) meets
  mercury 17, gems 20, then two crystal caverns at 22 and 23 tiles, and no sulfur.
- The player at (78,12) has a gold mine 7 tiles from home, and the player at (12,69) one at
  9 tiles. The player at (141,66) meets their first gold mine at 28 tiles.
- 15% of resource mines have another mine of the same resource within 10 tiles.
- 21% of visitables have a copy of their own kind within 10 tiles, and 10% within 6.

In the corpus of 159 maps:

- A town's nearest sawmill is a median 8 tiles away, its nearest ore pit 9.
- A map holds 0.77 sawmills and 0.73 ore pits per town.
- Sawmills and ore pits are 38% of the resource mines. Mercury, sulfur, crystal and gems
  are each about 12%, gold also 12%.
- Half the sawmills and ore pits sit within a day of the nearest home, and 6% sit 13 days
  or more away. Rare mines sit a median 3 days away, 8% at 13 days or more. Gold sits a
  median 4 days away, a third at 8 days or more, 23% at 13 days or more.
- The town count follows log towns = -2.5 + 0.41 log land + 0.68 log players (R² 0.6). That
  gives 15 towns for seed 25, against 24 generated.
- 8% of resource mines have another of the same resource within 10 tiles.
- 10% of visitables have a copy of their own kind within 10 tiles, and 3% within 6.

Done means, over seeds 1 to 10 at size 72 and seed 25 at size 144:

1. Every town, player or neutral, has its own sawmill and ore pit within 12 tiles on its own
   level (A1). They stand before any other mine near the town (A2). A town whose
   surroundings take no mine gets a warning that names it.
2. The mean town count over five seeds per size is within 20% of the corpus curve.
3. Each player's rare mines, nearest first, follow a round robin over mercury, sulfur,
   crystal and gems. A player meets every one of them the map offers before a second mine of
   any (A12). This holds when the player's share has at least one mine of each. Sawmills, ore
   pits and gold mines stay out of the round robin (A14).
4. At most 10% of rare mines have another of the same resource within 10 tiles.
5. No gold mine stands within 8 hero-days of any home. At each gold mine, the player who
   reaches it first and that player's nearest enemy arrive within 3 days of each other (A6).
6. At most 12% of visitables have a copy of their own kind within 10 tiles, and at most 4%
   within 6.
7. No new mine promise warning.

Out of scope:

- The visitable count. It runs 22% over the corpus curve on seed 25. It may move to a curve
  later, as the mines did.
- Dwellings and banks: their count and their spacing.
- The weekly producers, such as windmills and water wheels.
- The mine variant inside a resource, such as which sawmill sprite stands.
- The PortalStep crash on seeds 2 and 6 at size 144.

## 1b. Claims

1. Each player gets a wood and an ore mine of its own within the promise days. (promise
   allocator)
2. The town count is each terrain's area times the corpus town rate per tile. The towns
   already standing count inside it. (quota)
3. The resource mine count follows the corpus curve on land and players, split over the
   resources by their corpus counts. (quota, mine curve)
4. An object's kind is drawn from the corpus weights for the site's terrain, before the spot
   is known. (kind picker)
5. A kind the map already shows anywhere weighs 0.05 of its weight. (kind picker)
6. Neutral towns stand first in the map-wide pass, then the mines, then the rest. (placement)
7. Each mine family's count splits evenly over the players, then over the effort bands. Each
   mine draws its target day at random inside its band, family by family. (band plan)
8. An accent patch of 20 tiles or more holds a gold mine, an abandoned mine, a stat building
   or a dwelling, drawn by corpus weight. (landmarks)

## 2. Parts and concepts

### Level 1: parts

1. **Learning the counts** reads the corpus and states how a map's town count grows with its
   land and players. It owns the fit. It never knows the generator. It hands a count curve
   to Counting.
2. **Counting** states how many towns and mines of each resource a generated map holds. It
   never knows where an object stands. It hands the counts to the parts that place mines.
3. **Supplying towns** gives each town its own sawmill and ore pit, before any other mine.
   It owns where they stand. It never knows the rare or gold mines.
4. **Rotating rare resources** decides which rare resource each of a player's rare mines
   yields: mercury, sulfur, crystal or gems. It owns their order along the player's way out
   from home. It never knows wood, ore or gold, nor where a mine stands.
5. **Placing gold** decides where gold mines stand: far from every home, where rivals arrive
   at about the same time. It owns the contest between players. It never knows the other
   resources.
6. **Choosing a kind** picks which object of a family stands at a spot. It owns the variety
   of kinds, near and map-wide. It never knows how the spot was chosen.
7. **Checking the map** reads the finished map and reports what the player meets: each
   town's supply, each player's rare order, where gold stands, and how often a kind or a
   resource repeats nearby. It never knows how the map was made.

Flow: Learning runs once, when the corpus is mined. At generation, Counting fixes the town
count, one sawmill and one ore pit per town, and the rest of the curve for rare and gold
mines. Player towns stand, then their own pairs. Neutral towns stand, then their own pairs.
Rotating rare resources then deals the rare mines along each player's way out. Placing gold
stands the gold mines in contested land. The other objects stand, each with its kind chosen
at its spot. Checking reads the map at the end, in the generator's warnings and in the
readings report.

In plain words: learn from real maps how many towns a map of this size holds, give every
town its own wood and ore first, deal each player's rare mines out in turn, put the gold
where rivals fight for it, then avoid putting the same kind of object next to another one of
its kind.

### Level 2: concepts

**Learning the counts**

| Concept | Owns | Never knows |
|---|---|---|
| Count curve | The expected count at a land area and a player count: a power law in both. | What it counts. |
| Town curve fit | Fitting the count curve to the corpus town counts, as the mine curve is fitted. | How the curve is used. |

Count curve is a shared value type. The mine curve is one, the town curve another.

**Counting**

| Concept | Owns | Never knows |
|---|---|---|
| Town count | The towns a map holds: the town curve at the map's measure. | Terrain rates. |
| Pair count | The sawmills and ore pits a map holds: one of each per town. | The curve. |
| Curve rest | The rare and gold mines: the mine curve less the pairs, split by corpus count. | Which town owns a pair. |
| Mines still to place | The count of each mine family not yet standing. | Why a mine stood. |

**Supplying towns**

| Concept | Owns | Never knows |
|---|---|---|
| Town supply | The resources every town owns near it: wood and ore. | Rare resources and gold. |
| Nearness | The bound inside which a mine serves a town: tiles on the town's level. | Hero-days and players. |
| Own pair | Per town, one sawmill and one ore pit of its own, whatever stands near it. | Other towns' pairs. |
| Supply spot | The candidate spots for a mine near one town, nearest first. | Effort bands and players. |

**Rotating rare resources**

| Concept | Owns | Never knows |
|---|---|---|
| Rare resources | The resources the round robin deals: mercury, sulfur, crystal and gems. | Wood, ore and gold. |
| Player's mine way | One player's rare mines, ordered by target day, nearest first. | Which resource each yields. |
| Resource turn | The next rare resource for a player: the one furthest behind its share of that player's rare mines, ties in a fixed resource order. | Days and spots. |
| Player's share | Per player, the count of each rare resource it holds: the map's count of that resource split evenly over the players. | The order. |

Resource turn is the round robin. It is deterministic. The four shares are near equal, so
the turn cycles through all four before it repeats one. A rare mine already standing, such
as a promised one, counts toward its player's share and keeps its place on the way.

**Placing gold**

| Concept | Owns | Never knows |
|---|---|---|
| Contest | Per tile, the days between the first player to reach it and that player's nearest enemy. | Gold. |
| Far floor | The days from every home inside which no gold stands: the first effort band. | Enemies. |
| Gold spot | The tiles past the far floor, the most contested first. | Rare mines and towns. |

**Choosing a kind**

| Concept | Owns | Never knows |
|---|---|---|
| Kind weight | Each kind's corpus weight on the spot's terrain. | Other objects. |
| Map-wide variety | Weighing down a kind the map already shows. | Distance. |
| Near repeat | Weighing down a kind by the copies of it standing near the spot. | Kinds elsewhere on the map. |

**Checking the map**

| Concept | Owns | Never knows |
|---|---|---|
| Supply reading | Each town's distance to its nearest sawmill and ore pit. | Which towns are players'. |
| Way reading | Each player's rare mines nearest first, and the first repeat before the turn completes. | How the order was dealt. |
| Gold reading | Each gold mine's days from the nearest home and its contest. | How the spot was chosen. |
| Repeat reading | The share of visitables with a copy of their kind within 6 and 10 tiles, and of rare mines with one of their resource within 10. | Purposes other than visitables and mines. |

Nearness is a read-only reference that Supplying towns and Checking the map both consult.
Contest and Far floor are read-only references that Placing gold and Checking the map both
consult.

## 3. Invariants

1. Every town has its own sawmill and ore pit within nearness, or a warning names it. Owner:
   Supply reading, over the finished map. Own pair and Supply spot uphold it during
   placement.
2. No mine but a promised one stands before every town on the map has had its pair tried.
   Owner: Mines still to place, which hands out no other mine slot while Own pair has towns
   left.
3. The map holds one sawmill and one ore pit per town, and the curve rest of rare and gold
   mines. When the pairs alone pass the curve, the rest is zero and the overshoot is logged.
   Owner: Curve rest.
4. The same seed gives the same map. Owner: each part's one seeded draw order. Own pair
   visits towns in a fixed order.
5. Near repeat counts only copies on the spot's own level.
6. Rotating rare resources orders rare mines and never changes a count. Each player's count
   of each rare resource equals its share. Owner: Player's share. Resource turn upholds it by
   handing out exactly the share.
7. No gold mine stands inside the far floor. Owner: Gold spot, which never offers such a
   tile. A gold mine with no tile left stays unplaced, and the shortfall names it.

## 4. Forces and patterns

Forces:

- Wood and ore are mandatory for every town. A player needs both to build. They come first
  and unconditionally.
- The pairs must fit inside the mine curve. Seed 25 at the town curve needs 30 of its 70
  resource mines for wood and ore, 43%, against a 38% corpus share. At 24 towns it would need
  48, 69%, and starve the rare and gold mines.
- The town count drives the pair count, so the town count must follow the corpus first.
- The resource of a rare mine must follow the player's way out from home, not a random draw
  per family. The player feels the order, not the totals.
- Gold is the prize the players fight over. It belongs far from homes, where no player owns
  it alone.
- Wood and ore answer to towns, rare mines to each player's way, gold to the contest. The
  three vary apart from each other.
- Variety varies at two scales: map-wide coverage and local spacing. They answer different
  experiences and move independently.
- Placement must stay under a minute at size 144. No part may reprice every effort map.

Patterns:

- Between parts: one value handed along, as today. Counting hands counts. Each placing part
  hands its stood mines back to Mines still to place.
- Count curve: a plain value type, reused. No variation in shape.
- Town curve fit: a plain function, the mine curve fit applied to towns.
- Own pair and Supply spot: plain functions over the standing objects and the zone tiles,
  measured in tiles. No effort maps.
- Resource turn: a plain function, the largest-deficit sequence the band plan already uses
  for bands, applied to the rare resources over a player's rare mines sorted by target day.
- Contest: a plain function over the per-player days the placement already holds per tile.
- Map-wide variety and Near repeat: two plain weight factors multiplied into the kind
  weight. Two factors, not a role with variants, because both always apply.

The three mine resources differ in how they choose a spot, but nothing swaps one for
another. Each is a plain function its own part calls. No role is needed.

Claims:

1. Widened. The promise kept player wood and ore within days. Own pair now gives every town
   its pair within tiles, first. The promise reads wood and ore as met and stands none
   unless the pair lies past its days.
2. Rejected for towns. The town count takes the town curve, because the rate overshoots on
   large maps by 60% on seed 25. The standing towns still count inside it.
3. Reshaped. The curve still counts all resource mines. Wood and ore come off it first as
   one pair per town. Rare and gold split the rest by corpus count.
4. Reshaped. The kind is drawn at a known spot, because near repeat needs the spot.
5. Re-derived as map-wide variety. It stays.
6. Re-derived and split. Towns stand first, then their pairs, then the rare mines, then
   gold, then the rest. Each needs the one before it standing.
7. Reshaped for the rare mines, rejected for gold. The rare mines share one way per player,
   dealt in turn. Gold follows the contest, not the player split. Wood and ore follow the
   towns.
8. Reshaped. A landmark draws a gold mine only on a patch past the far floor and within the
   contest bound. Otherwise it takes the next kind.

Open lookups:

- Can the kind draw see the spot without a second draw per spot? This decides where the pick
  moves.
- Does the placement hold per-player days per tile, so Contest costs no new pricing? This
  decides whether gold stays under the time bound.
- Where do the teams live at the gameplay step? Contest needs enemies, not every other
  player.

SOLID check: each concept owns one thing. Near repeat is a new factor, added beside map-wide
variety, with no change to kind weight. Resource turn never knows days, and Player's mine
way never knows resources. Contest never knows gold, and Gold spot never computes days. No
role has variants. Supply spot never knows players, and Counting never knows why a mine
stood.

## 5. Mapping onto the existing system

Revision log:

- 2b Choosing a kind: the pick stays per site, read at the site's first candidate tile.
  Picking per spot would draw once per candidate and change the stream per try.

Parts:

- Learning the counts: **Reshape**. `MineCurve` (`core/priors/mines.py`) is the count curve
  under a mine name. It becomes `CountCurve`. The town curve is mined beside the mine curve
  (`corpus/mine/mines.py`) into `data/pp/towns.json`, loaded into the priors bundle.
- Counting: **Reshape**. The town group uses `RateRule` (`core/steps/gameplay/quota.py:120`).
  It takes `CurveRule` with the town curve. The resource group (`quota.py:121`) splits the
  whole curve by corpus count. It splits the curve less two mines per town over rare and
  gold instead, and the pairs count apart. The plan's slots per family
  (`core/steps/gameplay/placer.py:117`) are the mines still to place.
- Supplying towns: **New**, in `core/steps/gameplay/supply.py`. The gameplay step runs it
  for the player towns before the promise (`core/steps/gameplay/step.py`). `Placement.place`
  (`placer.py:122`) runs it for the neutral towns after the town slots, before any mine slot.
- Rotating rare resources: **Reshape**. `BandPlan.slots` (`core/steps/gameplay/bands.py:97`)
  plans each family alone, and `_target` (`bands.py:77`) draws each target day per family.
  The four rare families plan together instead: per player, their slots share one set of
  bands and target days from the pooled rare mine effort, sorted by target day, and Resource
  turn assigns their families. Standing rare mines enter through `standing_cell`
  (`core/steps/gameplay/siting.py:77`) as they do today.
- Placing gold: **Reshape**. Gold slots plan per player and band like any family. They plan
  with no player instead. `Siting._groups` (`siting.py:229`) orders tiles by spread, guard,
  own arrival, band and target day, from the per-player days it already holds in
  `tiles.days`. A gold slot orders by contest instead, and drops the tiles inside the far
  floor. The landmark draw (`core/steps/gameplay/landmark.py:51`) checks the same two bounds
  before it stands a gold mine.
- Choosing a kind: **Reshape**. `Picker.pick` (`core/steps/gameplay/pick.py:65`) draws per
  site before the spot. `Siting.stand` (`siting.py:199`) caches one pick per site. The pick
  gains the site's first candidate tile and the standing objects near it.
- Checking the map: **New** for the supply warning at the end of the gameplay step, beside
  the promise read (`step.py:202`). **New** readings lines in `cli/readings.py` for supply,
  the rare order, gold and repeats.

Concepts:

- Count curve: **Reshape**, renamed from `MineCurve`. Every name hit in the docs moves with it.
- Town count, Pair count, Curve rest: **Reshape** of `group_rules` (`quota.py:111`).
- Town supply, Nearness: **New**, in `core/reading/supply.py`, so the readings report and the
  step share one definition.
- Own pair, Supply spot: **New**, in `core/steps/gameplay/supply.py`. Supply spot orders a
  site's tiles by distance from the town and stands the mine through `ZoneSite.place`,
  guarded at the own-mine level of the promise (`core/steps/gameplay/allocate.py:30`).
- Rare resources, Player's mine way, Resource turn, Player's share: **New**, beside
  `band_sequence` (`bands.py:49`), which is the same deficit rule over bands. `BASIC_MINE_RES`
  (`core/reading/mines.py:13`) holds the rare four after wood and ore.
- Contest, Far floor: **New**, in `core/reading/contest.py`, so the step and the readings
  share them. Far floor is the first band edge, 8 days (`data/pp/effort.json`).
- Gold spot: **New** order in `Siting._groups`.
- Kind weight, Map-wide variety: **Exist**, in `Picker._weighted` (`pick.py:98`).
- Near repeat: **New** factor in `Picker._weighted`.
- Supply reading, Way reading, Gold reading, Repeat reading: **New**, in
  `core/reading/supply.py`, `core/reading/contest.py` and a repeat reader beside them.

What the existing system has that the design lacks:

- The promise allocator's day pricing. It serves players, not towns. It stays for the rare
  promise, and its wood and ore part finds the pairs already standing.
- The fair guard (`core/steps/gameplay/fair_guard.py`), which keeps each player's reach of a
  family even. For gold, Contest does that job. The fair guard still sets gold's guard level.

Lookups:

- Kind draw and spot: `Siting.stand` already holds each site's first group rows when it
  picks (`siting.py:196`), so the first candidate tile is free to pass. Resolved by the
  revision above.
- Per-player days: `Siting._groups` reads `tiles.days[0]`, one column per player, and
  already takes the soonest over players (`siting.py:240`). Contest is one more column
  reduction. Resolved.
- Teams: `enemy_pairs` (`core/steps/doors/rivals.py:50`) gives the enemy pairs from the
  team list. The gameplay step needs the same team list handed in. Resolved, with the
  hand-off as new wiring.

Claim check: the existing system follows all eight claims. The design keeps 5, reshapes 3,
4 and 8, widens 1, re-derives 6, rejects 2, and splits 7.

## 6. Slices

1. **Every town owns its pair.** Supplying towns, Pair count, Curve rest, Mines still to
   place and the supply warning. Done when every town on seeds 1 to 10 at size 72 and seed
   25 at size 144 has its own sawmill and ore pit within 12 tiles or a named warning, no
   other mine but a promised one stood before them, no new promise warning shows, `make
   check` passes and the goldens are updated.
2. **Towns on the corpus curve.** Learning the counts and the town count. Done when the
   five-seed mean town count per size is within 20% of the curve, and slice 1 still holds.
3. **Rare resources in turn.** Rotating rare resources and the way reading. Done when every
   player on the same seeds meets every offered rare resource before a second of any, at
   most 10% of rare mines have one of their resource within 10 tiles, and the counts per
   resource are unchanged.
4. **Gold in contested land.** Placing gold, the landmark check and the gold reading. Done
   when no gold mine stands within 8 days of a home, every gold mine meets the contest bound
   or is named in the shortfall, and the gold count is unchanged.
5. **No repeats side by side.** Near repeat and the repeat reading. Done when the readings
   report shows at most 12% within 10 tiles and 4% within 6 on the same seeds.

## 7. Assumptions

1. **Assumption**: 12 tiles on the town's level is near enough for a player to call a mine
   the town's own. **Decided**: nearness is 12 tiles, Chebyshev, from the town's visit
   tile to the mine's. **Basis**: the corpus median is 8 tiles to a sawmill and 9 to an ore
   pit. Player towns sit within 5 to 11 tiles. **If wrong**: Nearness, and done 1.
2. **Assumption**: "first" means before any mine near the town, and the rare promise may
   stand before neutral towns do. **Decided**: player pairs stand before the promise.
   Neutral pairs stand right after the neutral towns, before every mine slot. **Basis**:
   neutral towns stand inside the map-wide pass, after the promise, and the promise aims
   rare mines about 11 days from the players. **If wrong**: the flow, and neutral towns move
   before the promise.
3. **Assumption**: "unconditionally" means each town gets its own pair even when another
   town's mine stands within nearness. **Decided**: Own pair stands one sawmill and one ore
   pit per town, whatever stands near. **Basis**: the request, "place ore and saw mill first,
   unconditionally". The corpus holds 0.77 sawmills per town, so some corpus towns share.
   **If wrong**: Own pair and Pair count, which would count only towns with a gap.
4. **Assumption**: the pairs fit inside the mine curve once towns follow their curve.
   **Decided**: the pairs come off the curve, and an overshoot is logged. **Basis**: 30 of
   70 on seed 25, against a 38% corpus share. Between slices 1 and 2, 24 towns need 48 and
   leave 22 for rare and gold. **If wrong**: invariant 3, and the order of slices 1 and 2.
5. **Assumption**: a town's own zone, or the zones beside it, has room for two mines within
   12 tiles. **Decided**: Supply spot tries the town's site first, then the other sites on
   the level by distance. **Basis**: none measured. Neutral towns stand in zones of at least
   the town minimum area. **If wrong**: Supply spot, and the warning count.
6. **Assumption**: a gold mine is contested when the first player to reach it and that
   player's nearest enemy arrive within 3 days of each other, and far when it lies past the
   first effort band. **Decided**: contest bound 3 days, the promise gap. Far floor 8 days,
   the first band edge. **Basis**: the request, "gold go farther in contested areas". The
   corpus puts a third of gold mines past 8 days, against about a fifth of rare mines.
   **If wrong**: Contest, Far floor, and done 5.
7. **Assumption**: a map with no enemies, or a player with none, still has room for gold.
   **Decided**: with no enemy, Contest is unbounded and Gold spot orders by days from the
   nearest home, farthest first. **Basis**: none. **If wrong**: Gold spot.
8. **Assumption**: a near-repeat factor of 0.1 per copy within 10 tiles brings the repeat
   share near the corpus. **Decided**: that factor, tuned in slice 5 against done 6.
   **Basis**: none. The corpus shares are 10% and 3%. **If wrong**: Near repeat.
9. **Assumption**: the town curve fitted on all towns, player ones included, matches how the
   generator counts. **Decided**: the curve gives all towns, and the standing player towns
   come off it. **Basis**: the quota already counts standing towns inside the town count.
   **If wrong**: Town count.
10. **Assumption**: the new parts add no measurable time at size 144. **Decided**: tile
    distances for the pairs, one column reduction for Contest, no effort repricing.
    **Basis**: about 15 towns, two mines each. Contest reads the days the placement already
    holds. **If wrong**: Supply spot and Contest.
11. **Assumption**: every slice changes the goldens. **Decided**: every slice regenerates
    them. **Basis**: each slice moves mines, and the mines feed the placement order. **If
    wrong**: nothing to re-derive.
12. **Assumption**: the player feels the rare order along their way out, nearest first, more
    than the spacing between any two mines. **Decided**: the round robin runs per player
    over target days. Shared rare mines from the promise count in the turn of the player who
    reaches them first. **Basis**: the request, "mine type should be a round robin, not
    random". **If wrong**: Player's mine way, and done 3.
13. **Assumption**: a mine stands near its target day often enough that dealing by target day
    gives the order the player meets. **Decided**: done 3 is read on the finished map, by
    distance from each player town. **Basis**: none measured. Siting sorts tiles by band, then
    by distance to the target day. **If wrong**: Rotating rare resources needs the order read
    at standing time, not at planning time.
14. **Assumption**: sawmills, ore pits and gold mines need no round robin. **Decided**:
    Rotating rare resources deals only mercury, sulfur, crystal and gems. **Basis**: the
    user's rule, "the round robin does not apply to ore pit, saw mill and gold mine". **If
    wrong**: Rare resources, and done 3.
