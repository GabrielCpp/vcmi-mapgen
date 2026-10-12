# Neutral town spacing

Status 2026-10-12: the town's fair guard is superseded. A neutral town draws its guard
from the corpus record of towns like every family, and the placer evens out each player's
claimed value over the first 40 hero-days (global-placement.md, R18, R19 and A17). Spacing
still ranks a town's spot first. Since 2026-10-12 the even reach is a rank, not a filter:
a town takes the least uneven spot with room when no even one is left.

Disclosure: I read the town siting code, the fair guard and the zone site before this skill
loaded, while diagnosing seed 1024 at 144. Every design decision that code carries and that
this note touches is a claim in 1b.

## 1. Problem

A player on a large map finds neutral towns bunched on one side, one or two days apart,
while wide open land elsewhere holds none. On seed 1024 at 144, five neutral towns stand
in the east within 9 to 15 tiles of each other. The six largest empty zones, 600 to 1800
tiles each, hold no town. The towns are bunched because they move to keep the game fair:
each one goes where every player reaches about the same number of towns at about the same
distance.

Done looks like this to that player:

- Towns spread over the land the way hand-made maps spread them. Measured per level as a
  town's nearest-town distance over the spacing of an even grid of the same count on the
  same land, the corpus gives a median of 0.96 (p10 0.73, p90 1.42). The closest pair
  gives a median of 0.77 (p10 0.52). Seed 1024 at 144 gives 0.38 and 0.25 today. Done is
  the median nearest within the corpus p10 to p90 and the closest pair at or above the
  corpus p10, on every seed of the sweep.
- A neutral town that one player would reach far earlier than the others has a monster at
  its door. The monster is strong enough that, counted in hero-days like every other guarded
  object, no player reaches more towns per effort band than the others allow today.

Out of scope:

- Player towns. They keep their placement, and no monster ever stands at a start.
- The number of neutral towns, which keeps its corpus curve.
- Each town's sawmill and ore pit, which keep their 12-tile rule.
- Mines, whose guards keep their own rules.
- Rare mines, which keep their turn along each player's way.

## 1b. Claims

From the current code:

1. A neutral town serves one player, an effort band and a target in days, split evenly
   over the players and the bands by the corpus effort of towns. (bands)
2. A town's spot ranks by fairness first, then its player's arrival, then its band, then its
   target days. (siting)
3. A town takes no fair guard. A town or a mine counts no guard in reach, "since its guard
   comes with it". (families, siting)
4. One town per zone, and only in a zone of 150 tiles or more. (siting)
5. A large object tries the most open ground of its spot's neighbourhood first. (siting)

## 2. Parts and concepts

### Level 1

1. **Town count** says how many neutral towns the map holds. It never knows where they go.
   It hands a count to town spotting.
2. **Town spotting** picks the spot of each neutral town from the land and the towns
   already standing. It owns where. It never knows players or effort. It hands a ranked
   list of spots to the fairness gate.
3. **Fairness gate** prices a spot for each player in hero-days, beating any guard. It
   owns the weakest door guard that keeps the players even. It refuses a spot no guard
   evens. It never knows spacing. It hands each surviving spot its guard level.
4. **Standing** puts the town and its guard on the ground. It records the town so that
   spotting and the gate see it next time. It never knows why the spot won.

Flow: the count gives n. For each town in turn, spotting ranks the spots. The gate keeps
the spots it can even and names their guard. Standing tries them in rank order and records
the first that takes. Then the next town is placed, with every standing town in view.

In plain words: decide how many towns, put each in the biggest gap between towns, and if
that gap sits close to one player, put a monster at its door strong enough to even it out.

### Level 2

Town count: no change.

Town spotting:

| Concept | Owns | Never knows |
|---|---|---|
| Town gap | per spot, the tile distance to the nearest standing town on its level, player towns included | players, guards, zones |

Fairness gate:

| Concept | Owns | Never knows |
|---|---|---|
| Effort | per spot and player, the hero-days to visit past a guard of each level | towns as such |
| Town reach | per player and band, the towns that player reaches | spots not yet stood |
| Fair guard | the weakest guard level that keeps town reach even at a spot | spacing |

Standing:

| Concept | Owns | Never knows |
|---|---|---|
| Door guard | the monster in front of a town's entrance at the gate's level | why that level |

Effort and Fair guard are the same concepts every family uses. Town reach is one
instance of the reach each family keeps.

## 3. Invariants

1. No neutral town widens the players' reach gap beyond the slack the other families keep.
   Owner: Fair guard, which refuses the spot.
2. A town's own guard counts in its reach, the same as for any guarded family. Owner: Town
   reach.
3. No monster stands at a player town. Owner: the start room rule, unchanged.

## 4. Forces and patterns

Forces:

- F1. Spacing and fairness change for different reasons. Spacing follows the corpus look.
  Fairness follows the effort model.
- F2. Fairness must use the one hero-day effort model every family uses (user,
  2026-10-11).
- F3. Where a town stands stays deterministic for a seed.
- F4. Generation at 144 has little time to spare (57 to 60 s CPU).

Patterns:

- Between parts: one value handed along per town, the ranked spots. Spotting ranks and the
  gate filters, so neither knows the other's rule (F1). No new protocol, since neither has
  variants today.
- Town gap: a plain function over the standing towns, recomputed per town. Ten towns over
  about 20,000 tiles cost a few milliseconds (F4).
- Fair guard: the existing function, now fed towns (F2).
- Rank order for a town slot: fairness tier, then the largest town gap, then the weakest
  guard, then the seeded random draw (F3).

Claims:

- 1 rejected: a town serving a player and a target day ties it to that player's distance,
  which is what bunches the towns. A town slot serves no player, like a gold mine. Town
  reach still splits by player through the gate.
- 2 rejected for towns: spacing replaces arrival, band and target days.
- 3 rejected for towns: a town's guard is a fair guard now, so it counts. Kept for mines,
  out of scope.
- 4 rejected (user, 2026-10-11): zones got small, so a zone says nothing about how far
  apart two towns stand. Town gap replaces it. The 150-tile floor goes with it (A6).
- 5 kept: a town is large, so it already tries the most open ground of its spot.

Open lookups, resolved in section 5:

- L1. Does a slot with no player get a fair guard today?
- L2. Can a town stand with a guard in front at all?

## 5. Mapping onto the existing system

Revision log:

- Section 2, Town host and Town mark removed, section 3 invariant 1 removed, claim 4
  rejected. The user ruled one town per zone out, since zones got small.
- Section 2, Town gap: it counts the map edge as a mirror town, capped at twice the edge
  distance. Without it, the first town of a level with no town yet ranks every tile alike.
- Section 2, Town spotting: a spot needs 238 tiles of land within 12 tiles, the corpus
  tenth percentile around a town. A6 triggered: underground spots in rock left the town's
  sawmill and ore pit no ground. The floor keeps every neutral town on the surface on seed
  1024, as the old code did.
- Section 2, Standing: a town's sprite may hang outside its zone, and so may its sawmill
  and ore pit. A guarded town stands on the town footing with its guard in front. Zones got
  small, and the strict footing stood no town at all.
- Section 2, Standing: a town tries every site, as a mine does. Every town spot shares one
  fair tier, so the cap of a few sites per tier stopped at the first small zones.
- Section 2, Town spotting: an unguarded spot whose gap reaches 80% of the largest ranks
  before a guarded one. A3 triggered: 6 of 10 towns on seed 1024 carried a monster, against
  11% on hand-made maps.
- Section 2, Standing: a town keeps no gap around its body. A5 triggered: other bodies kept
  2 free tiles from a town, and a town in a small field left no room for its ore pit. Hand-made
  maps put the nearest object against or 1 tile from a town on 62% of towns (user, 2026-10-11).
- Section 1, out of scope: the other families now follow the towns. Every family but the
  rare mines serves no player. It keeps its band and target, map-wide. A guard lifts a cheap
  tile into its band, and the gap to the nearest object or home ranks the tiles of a band.
  A3 had a sibling: the top-left start of seed 1024 reached 1300 tiles within 8 days and
  got 3 objects there, because each player's objects looked for its own unguarded days.
  The user ruled that cheap land takes stronger monsters, not fewer objects (2026-10-11).
- Section 1, out of scope: no guard stands on a start's way out of its home place (user,
  2026-10-11). The top-right start of seed 1024 reached 56 tiles within 8 days, behind a
  level 3 door out of a 150-tile home. A door a player crosses before its land holds 600
  tiles now stays open, and no gameplay guard stands on the walk out of a home zone.

- Town count: **Exists**, the corpus town curve in `quota.py`.
- Town gap: **New**, a function in `siting.py` beside `_groups`, read only for town slots.
- Effort: **Exists**, `Tiles.priced` and `EffortMap.visits`.
- Town reach: **Reshape**. `reach_guard` in `reading/families.py:117` returns 0 for a town,
  so a guarded town would count as unguarded on every reprice. Town comes off `UNGUARDED`.
  Mines stay on it. Its docstring changes to name mines only.
- Fair guard: **Reshape**. `_fair` in `siting.py:397` gives level 0 to `UNGUARDED`, which
  holds towns. That is fixed by the same change. L1: `_groups` computes the fair guard only
  in the player branch or the gold branch (`siting.py:375`). A town slot with no player
  gets no fair tier at all, so a town branch is new: fair tier and guard as in the player
  branch, with the town gap in place of arrival, band and target.
- Door guard: **Exists**. L2: `ZoneSite.try_commit` stands a guard for any object passed a
  level (`site.py:477`), and `Siting._try` already passes the level with a mine footing.
- Slot planning: **Reshape**. `Placement._deal` deals towns through `BandPlan` with a player
  and a band. Towns get the gold path: n slots serving no player.

What the code has that the design lacks:

- `hosts` in `siting.py:115`, which admits a town only in a zone of 150 tiles with no town
  yet. Waste once Town gap ranks the spots. Its town branch goes.
- `ZoneSite.town_center`, the zone's town mark. Neutral spotting no longer reads it.
  Player town placement still reads it (`step.py:89`), and it stays for that. A guarded
  town skips the mark (`site.py:497`), which no longer matters.

- The player split's `starts` rotation for towns. Waste for towns once they serve no
  player.
- `slot_order` places the far band first. Town slots with no band keep their purpose rank
  only. No loss.

Claims against the code: the code follows 1 to 5. The design keeps 5, and drops 1 to 4 for
towns.

## 6. Slices

1. **Towns spread, fairness by guard.** Town slots serve no player. They rank by fair tier,
   then town gap, then weakest guard. Towns come off `UNGUARDED`, and `hosts` drops its
   town rule. Touches Town gap, Fair guard and Town reach. Done when seed 1024 at
   144 shows a median nearest within 0.73 to 1.42 of even spacing and a closest pair at or
   above 0.52. The step log shows no town supply shortfall the old map lacked. `make check`
   passes after `make golden`.
2. **Spacing in the readings.** `readings` prints town spacing per level beside the corpus
   spread. The sweep checks it on 10 seeds at 72 and 144. Done when every sweep seed sits
   inside the corpus band (A2).

## 7. Assumptions

1. **Assumption**: placing each town in the largest gap gives the corpus spread, not a
   pile on the map edges. **Decided**: largest gap first, with no edge term. **Basis**:
   the homes already sit near edges and corners, so they fill the edge gaps. That is a guess
   for the 2-player maps. **If wrong**: Town gap gains the map edge as a pseudo-town, in 2
   and 4.
2. **Assumption**: the gate keeps enough spots that spacing still decides. With top guards
   at 45 days and more, any spot evens out. **Decided**: fairness tier stays first.
   **Basis**: the fair guard reaches the toll's top level (`fair_guard.py:20`). **If
   wrong**: towns fall back to the clustered spots. Slice 1's done-when shows it.
3. **Assumption**: a monster at a neutral town's door matches hand-made maps often enough.
   **Decided**: no cap on guarded towns. **Basis**: 11% of corpus towns, player towns
   included, have a monster touching the door, so a larger share of the neutral ones do.
   **If wrong**: a cap per map in 2 and 4.
4. **Assumption**: ten towns' fair guards add under a second at 144. **Decided**: no cache.
   **Basis**: every other family already runs the same fair guard per slot. **If wrong**:
   cache the town gap per standing town, in 4.
5. **Assumption**: the sawmill and ore pit still fit within 12 tiles of a town in an open
   field. **Decided**: no change to supply. **Basis**: a town in an open field has more room
   around it, not less. **If wrong**: supply warnings rise in slice 1's log.
6. **Assumption**: with no zone floor, the largest gap still lands a town on open ground
   and not in a sliver. **Decided**: no room rule beyond the open-field footing.
   **Basis**: the largest gap lies far from every town, and a large object already tries
   the most open ground of its spot (claim 5). **If wrong**: Town gap counts only spots
   with a town's room around them, in 2.
