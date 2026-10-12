# One map-wide stock of towns and mines

Status 2026-10-12: Balancing's fair guard is superseded. Each family draws its guard from
its corpus record, and the placer evens out each player's claimed value over the first 40
hero-days (global-placement.md, R18 and R19).

Disclosure: before this note I had read the gameplay placement code, the mine quota, the
town siting and the town supply pairs, and I wrote the neutral town spacing note. The
decisions they carry are listed as claims in 1b.

## 1. Problem

A player on a small map finds fewer rare mines than a map of that size should hold, and
more sawmills and ore pits than the corpus would put there. A 36 map, 2 players, seeds 1
to 6, holds 5 to 11 resource mines where the corpus curve asks for 8 to 12. Wood and ore
take 33% to 64% of them, where the corpus 36 maps give a median of 45%. Four seeds of six
miss a rare mine the plan asked for, and five of six miss their gold mine. The cause is
the rule that gives every town its own sawmill and ore pit: each pair takes two slots off
the rare and gold mines, and 3 towns on a 36 map take 6 of about 12. On any map, a neutral
town or a moved player town can lose its spot to a fixed land rule that fits one map size.

In the corpus of 159 maps:

- A map holds a median 1.6 to 2.0 sawmills and ore pits per town, 2.0 on 36 maps.
- Wood and ore make 45% of the resource mines on 36 maps and 35% to 36% on larger ones.
- A town's nearest sawmill grows with the land: `log d = 0.75 + 0.174 log land`, so 7.4
  tiles at 36, 9.4 at 72 and 12.0 at 144. The ore pit fit is the same within 0.3 tiles.
  The fit explains 3% of the spread between towns (R² 0.03). Half the towns sit between
  0.6 and 1.6 times the curve.
- At 72 and above, a quarter of the towns sit 14 tiles or more from their nearest
  sawmill, past the 12 tiles the current pair rule forces.

Done means, over seeds 1 to 6 at size 36 with 2 players, seeds 1 to 10 at size 72 and
seeds 25 and 1024 at size 144:

1. The mean count of resource mines, all seven resources, is within 20% of the corpus
   curve at each size.
2. Wood and ore make a share of the resource mines within 0.1 of the corpus median at
   that size.
3. The median tiles from a town to its nearest sawmill, and to its nearest ore pit, lie
   between 0.6 and 1.6 times the fitted curve at the map's land.
4. The mean town count is within 20% of the corpus town curve at each size.
5. No mine promise broken that the same seed does not break today.
6. No rule that admits or refuses a town or a mine spot names a count of tiles.

Out of scope:

- Rare mines with no spot at all on seeds 2 and 6 at 36. They miss on HEAD too, where
  water splits the land (A6).
- Hero-day thresholds such as the 14-day promise. They are time, and they get their own
  review.
- Where the player towns stand in their home zones.

## 1b. Claims

1. Every town owns a sawmill and an ore pit within 12 tiles, stood right after the towns
   and before any other mine near it. (town-supply-and-variety.md, done 1; the gameplay
   step)
2. Each own pair takes two slots off the curve count of the rare and gold mines. (the mine
   quota)
3. Sawmills and ore pits stand outside the resource mine count, as town pairs and as
   promised mines. (the mine quota)
4. A neutral town spot needs 238 land tiles within 12 tiles, the corpus tenth percentile.
   (neutral-town-spacing.md)
5. A player town that cannot fit its zone moves to a zone of 150 tiles or more, or 600
   when that zone already holds a town. (the gameplay step)
6. A town with no sawmill or ore pit within 12 tiles gets a warning. (the gameplay step)
7. Each player reaches a mine of each basic resource within 14 hero-days. (the gameplay
   step)
8. Neutral towns rank by spread tier, then town gap, then fair guard. (neutral-town-spacing.md)

## 2. Parts and concepts

### Level 1

1. **Counting the stock.** It owns how many towns and how many mines of each resource the
   whole map holds. It never knows where any of them stands. It hands the counts to the
   other parts.
2. **Keeping each player supplied.** It owns the mines each player must reach early. It
   never knows the rest of the stock. Its mines count against the stock.
3. **Choosing spots.** It owns where each counted object stands among the free land. It
   never knows how the counts were drawn.
4. **Balancing effort.** It owns the hero-days each player pays to reach a spot and the
   guard that evens them. It never knows which object will stand there.
5. **Reading the result.** It owns how the finished map compares with the corpus. It never
   changes the map.

Flow: Counting draws the stock. Supply stands each player's promised mines, and they come
off the stock. Choosing stands what is left, asking Balancing for each spot's fair guard.
Supply checks its promise again after Choosing and repairs a broken one. Reading reads the
finished map.

In plain words: decide how much the whole map holds, make sure every player can reach wood
and ore, put the rest where it is spread out and fair, then check the map against the real
ones.

### Level 2

**Counting the stock**

| Concept | Owns | Never knows |
|---|---|---|
| Town stock | The number of towns, from the corpus curve on land and players | Mines |
| Mine stock | The number of resource mines of all seven resources, from the corpus curve | Towns |
| Resource split | Each resource's share of the mine stock, by its corpus weight | The curve |

The corpus curves are a read-only reference every part may consult.

**Keeping each player supplied**

| Concept | Owns | Never knows |
|---|---|---|
| Player promise | Each player reaching a mine of each basic resource within the promise days | The stock's other mines |

**Choosing spots**

| Concept | Owns | Never knows |
|---|---|---|
| Spread | An object's gap to the nearest standing object of its kind | Effort |
| Supply pull | A wood or ore mine's tiles to the town standing furthest from that resource | The stock |
| Spot order | The order of the ranking keys for each kind of object | How each key is computed |

**Balancing effort**

| Concept | Owns | Never knows |
|---|---|---|
| Hero-day effort | The days a player pays to reach a tile, travel plus guards | Objects |
| Fair guard | The guard level that keeps a spot from widening the effort gap | Families |

**Reading the result**

| Concept | Owns | Never knows |
|---|---|---|
| Supply distance curve | The corpus fit of a town's tiles to its nearest wood or ore over land | Generated maps |
| Supply reading | A finished map's median town distance to wood and to ore, against the curve | The rules that placed them |
| Stock reading | A finished map's counts and wood and ore share, against the corpus | The rules that placed them |

## 3. Invariants

1. Every resource mine on the map counts once against the mine stock, promised or not.
   Owner: Mine stock. Player promise upholds it by handing its mines to the count.
2. The promise wins over the stock: when the promised mines pass a resource's share, the
   other resources lose slots, never the promise. Owner: Mine stock.
3. No ranking key refuses a spot by a count of tiles. Owner: Spot order.
4. The supply pull never wins against fairness. A spot that widens the effort gap loses to
   one that does not. Owner: Spot order. Fair guard upholds it.
5. Each player reaches each basic resource within the promise days, or the step warns.
   Owner: Player promise.

## 4. Forces and patterns

Forces:

- Map size runs from 36 to 144 and more, and one rule must hold across it. Every threshold
  derives from the map or from a corpus fit over land.
- A town changes owner during play, so a town has no player to keep fair. The player
  promise answers supply per player, and the town only pulls.
- The corpus says towns sit near wood and ore, but loosely (R² 0.03). A loose pull
  answers it, a hard gate does not.
- What the map holds and where it stands vary apart. The count stays apart from the
  siting.

Patterns:

- Between parts: one plan of slots handed along, as today. No new pattern.
- Mine stock: a plain function over the corpus curve. Resource split: the existing largest
  remainder split.
- Supply pull: one more key in the existing ranking order, computed by a plain function.
- Supply distance curve: a least squares fit of log distance on log land, stored with
  the priors. A distance is a positive measure, not a count, so the log-normal fit the
  mine and town curves use suits it. The negative binomial the family counts use does
  not. The curve also keeps the quartiles of its residual, the 0.6 and 1.6 of done 3.
- Reading: plain functions.

Claims:

1. Rejected. The corpus breaks it: a quarter of its towns at 72 and above have no sawmill
   within 14 tiles. The pull and the promise replace it.
2. Rejected with claim 1.
3. Rejected. Wood and ore join the mine stock, so the curve counts them like the others.
4. Rejected. A fixed tile floor does not scale. Spread and fairness rank the spots alone
   (A3).
5. Rejected. The largest zone that fits takes the town, with no floor.
6. Rejected. The supply reading replaces the warning.
7. Kept. Force: a town has no player, so supply is per player.
8. Kept.

Open lookups:

- Where the pull sits in the spot order. Decided: in place of the target days key, the
  last key before the random draw (A1).
- Whether promised wood and ore count against the stock today. Decided by the mapping.

## 5. Mapping onto the existing system

Revision log: none.

| Item | Verdict | Where and why |
|---|---|---|
| Counting the stock | Reshape | `gameplay/quota.py` `group_rules` |
| Town stock | Exists | `quota.py` town group on `TOWN_CURVE` |
| Mine stock | Reshape | `quota.py:134` leaves the supply families out of `resource`, and `per_town` takes two slots per town off the rest. The code is wrong: the curve was fitted over all seven resources. |
| Resource split | Exists | `quota.py` `split` by corpus weight |
| Player promise | Exists | `allocate.py` `keep_promise`. Its mines stand before the map-wide pass and `placer.py:151` counts standing objects against their family. Wood and ore have no family in the quota today, so they count against nothing. After the change they count. |
| Choosing spots | Reshape | `gameplay/siting.py` |
| Spread | Exists | `siting.py` `town_gap` and `_gaps` |
| Supply pull | New | A key in the shared-slot branch of `Siting._groups` for wood and ore slots |
| Spot order | Reshape | `siting.py:383` gates towns on `town_room >= TOWN_ROOM`. `step.py:92` gates the moved player town on `TOWN_MIN_AREA`. |
| Balancing effort | Exists | `fair_guard.py`, `reading/effort.py` |
| Supply distance curve | New | Fitted beside the count curves in `corpus/mine/counts.py`, loaded with the priors |
| Supply reading | Reshape | `reading/supply.py` keeps `town_supply` and drops the `NEAR` gate and `supply_gaps`. The `readings` report prints the medians beside the curve. |
| Stock reading | Exists | `corpus_match.py` and `readings.py` tally counts |

The existing system has these the design lacks. All are waste once the pairs go:

- `gameplay/supply.py`: `stand_pairs`, `NearFooting`, `supply_spots`.
- `placer.py`: `Plan.paired`, `_pairs`, `trim`, and the "pairs pass the mine curve" warning.
- `quota.py`: `Group.per_town` and `paired`.
- The `stand_pairs` calls in `step.py` and `conftest.py`, and the `NEAR` import in
  `siting.py`.
- `SUPPLY_FOOTING` in `placement/site.py`. Only the pairs use it.

## 6. Slices

1. **Wood and ore join the stock, and the pairs go.** Touches Mine stock, Resource split,
   Player promise and the waste list. Done when done 1, 2 and 5 hold at 36 and 72, and
   `make check` passes.
2. **The supply pull.** Touches Supply pull and Spot order. Done when done 3 holds at 36,
   72 and 144, measured with a scratch script against the fitted curve.
3. **No tile floors for towns.** Touches Spot order. Done when done 4 and 6 hold, and no
   player town goes missing at 36.
4. **The supply reading.** Touches Supply distance curve and Supply reading. Done when
   the `readings` report prints both medians beside the curve, the supply warning is
   gone, the golden hashes are updated and the docs name no deleted function.

## 7. Assumptions

1. **Assumption:** without the pairs, the pull keeps the median town distance to wood and
   ore within 0.6 to 1.6 times the curve. **Decided:** the pull is a late ranking key, not
   a gate. **Basis:** the corpus holds 1.6 to 2.0 wood and ore mines per town, so the stock
   alone puts about as many near towns as the pairs did. **If wrong:** section 4 open
   lookup and Spot order: move the pull ahead of the town gap.
2. **Assumption:** the promise fits inside the stock on a 2-player 36 map. **Decided:**
   invariant 2 lets the promise win. **Basis:** the promise needs at most 4 wood and ore
   mines with 2 players, and the stock gives 45% of 8 to 12, so 3.6 to 5.4. **If wrong:**
   rare mines lose slots on the smallest maps. Mine stock then counts the promise first and
   splits the rest over the other resources.
3. **Assumption:** without the room floor, neutral towns still avoid cramped pockets,
   because the gap rank favours open middle ground. **Decided:** drop `TOWN_ROOM` with no
   replacement. **Basis:** none. **If wrong:** Spot order takes a relative floor, the mean
   room of the player homes on the level, as the doors already do.
4. **Assumption:** one corpus share of wood and ore suits every size. **Decided:** Resource
   split keeps one corpus weight per resource. **Basis:** the share is 45% at 36 and 35%
   to 36% above, and done 2 allows 0.1. **If wrong:** fit the share over land like the
   counts.
5. **Assumption:** the size-72 maps in `out/` are from 2026-10-10, before the current
   uncommitted work. **Decided:** slice 1 regenerates its baseline first. **Basis:** file
   dates. **If wrong:** nothing.
6. **Assumption:** seeds 2 and 6 at 36 miss rare mines because of the land, not the
   pairs. **Decided:** out of scope. **Basis:** the same warnings on HEAD. **If wrong:**
   slice 1 fixes them too.
