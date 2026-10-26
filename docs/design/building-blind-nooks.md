# Building-blind nooks

Status 2026-10-26: approved and built as slice 1. This note replaces the resident-prize
draft of 2026-10-25, which the user turned down.

Disclosure: I read the loot step, its nook finder, its cache placer, the kept ways and the
family guard draw before this skill loaded, while diagnosing the open nook at 0,97 on seed 15
at 144. Every design decision that code carries and that this note touches is a claim in 1b.
I checked each part and concept name against the test "would I have named this without
having seen the code?" Two names failed it and were changed: "barred tiles" became the
obstacle of the walkable land, and "approach" became the door.

## 1. Problem

A player walks into a dead-end nook that holds a building and finds it open, with no monster
at the mouth and no treasure beside the building. A nook of the same shape with nothing in
it gets a monster, a ward artifact and a few pickups. The user saw it at 0,97 on seed 15 at
144, where a nook held the School of Magic and stood open while the empty nooks around it
were guarded. Today a nook that holds any building's door is never a nook, by construction.
On the ten verify maps at 72, 1 guarded nook per map holds a building. At 144 it is 2.

Done looks like this to that player:

- A nook is found whatever buildings stand in it, one or many. It is guarded and filled like
  any nook of its shape: a monster at the mouth, a ward artifact at the deepest free tile,
  loose pickups on the other free tiles, and the buildings stand among them. On seed 15 at
  144, the nook with mouth 20,103 that holds a fountain and two Huts of the Magi (doors
  19,106, 25,109 and 21,110) shows a guard at 20,103 and a ward inside.
- About 10 guarded nooks per 72 map hold a building (8 to 17), and 33 at 144.
- No guard and no pickup ever stands on a building's door.
- No such guard stands on a player's way to a promised mine, on a player's way out of the
  home zone, on a way by sea, in a start room, or between a town and its own sawmill or ore
  pit. The mine-promise warnings stay at today's count: two lines on seed 4 at 72, none on
  the other verify maps.

Out of scope, and agreed by approving this note:

- Fairness at 72 drops. The value a player claims first against the best player's falls from
  0.347 to 0.314 within 10 days and from 0.414 to 0.358 within 20 days. Both were already
  below the corpus medians of 0.669 and 0.568. At 144 the same readings fall from 0.976,
  0.744, 0.682 and 0.684 to 0.820, 0.636, 0.557 and 0.581, which brings them to the corpus
  medians of 0.603, 0.561, 0.558 and 0.543 (A3).
- Shallow nooks lose about 17% of their loose pickups at 72 and 12% at 144. Deep nooks gain
  more than that, so each map holds about 17% more loose pickups in nooks overall.
- The seer-hut quests move on 2 of the 11 verify maps, since they read the same nooks.
- About 1 in 13 of today's guarded nooks moves its cut, since a nook may now run past a door.
- A guard priced by the worth of the buildings inside. The guard level comes from the corpus
  spread at the place's hop, like every nook guard (A7).
- Moving a building so that its nook gets a free tile.
- The open clearings far from any object, parked on 2026-10-25.
- Nooks in zones without a zone plan. They keep today's path (A6).
- A loose pickup standing on a Quest Gate's door, which happens today on one verify map and
  comes from the order of the steps, not from the nooks.

## 1b. Claims

From the user, 2026-10-25:

1. Buildings are not considered in a nook.
2. One or many buildings in a nook can make a pocket.
3. A nook with buildings gets the same guard, ward and pickups as any nook.
4. Only the kept ways exclude a guard. No building kind is excluded.
5. Promised mines and town routes stay out.

From the code I read before the skill loaded:

6. A nook that holds any object's door is no nook (the room finder and the mask matcher both
   reject it).
7. Every guarded nook holds an artifact at its deepest free tile, its tier set by the guard's
   level, held back for the set dealer.
8. A nook guard's level comes from the corpus spread at the place's hop, never from the
   prize's worth.
9. In a planned zone, a deep nook is guarded and a shallow nook stays open with a few
   pickups.
10. A nook guard is refused when its zone of control covers a kept way or a start room, and
    when it would cut a town off from its own sawmill or ore pit.
11. The seer-hut quests hide their artifact in the tiles of the deep nooks.

From the user's standing rules:

12. Each gameplay family draws its own guard from its corpus record, guarded or not and the
    level (2026-10-12).
13. No guard is added to fix an effort gap (2026-10-12).
14. Coverage and the full plan come before fairness (2026-10-12).

## 2. Parts and concepts

### Level 1

1. **The nooks.** Finds the dead ends of the walkable land: each nook's tiles, its mouth
   and its shape, shallow or deep. Owns the geometry. Never knows what stands inside a nook.
   Hands each nook to the filling and to the seer huts.
2. **The filling.** Decides what a hero wins past the mouth: the ward artifact at the
   deepest free tile and the loose pickups on the other free tiles. Owns what is added
   inside a nook. Never knows the guard tile or the guard level.
3. **The guarding.** Picks the guard's tile at the mouth and its level, and stands the guard
   once the filling stands. Owns the monster at the mouth. Never knows what the filling is.
4. **The kept ways.** Holds the tiles no guard may close: each player's way to a promised
   mine, out of the home zone and by sea, each start room, and each town's way to its own
   sawmill and ore pit. Owns the refusal. Never knows nooks.
5. **The record.** Writes what each nook got: its outcome, its guard and its ward. Owns the
   decision line and the overlay colour. Never decides anything.

Flow. The nooks are found once per level over the finished walkable land, with only solid
cells as obstacles. The seer huts read the deep nook tiles. For each nook, the guarding asks
the kept ways about the mouth tile and draws the level. The filling stands its ward and
pickups on the free tiles. The guarding then stands the guard. The record writes each nook
at the end of its turn.

In plain words: the generator finds the dead ends and ignores the buildings in them. It
fills each dead end with treasure on the ground the buildings leave free, never on a
building's door. A monster goes at the mouth when the dead end is deep, unless it would stand
on a door, on a player's way to a promised mine or out of the home zone. Each dead end's
fate is written down.

### Level 2

**The nooks**

| Concept | Owns | Never knows |
|---|---|---|
| Walkable land | the tiles a hero stands on, moving 8 ways | objects' purposes |
| Obstacle | the solid cells of objects, which no nook may hold | doors |
| Nook | a bounded set of walkable tiles reached only through one mouth | what stands inside |
| Nook shape | shallow or deep, from area and depth | the filling |
| Nook group | the candidate cuts of one physical nook, best first | guards |

A door is walkable. It belongs to the land, not to the obstacle.

**The filling**

| Concept | Owns | Never knows |
|---|---|---|
| Door | the tile a hero stands on to visit an object | nooks |
| Free tile | a nook tile that holds no object and is no door | the guard |
| Ward | the artifact at the deepest free tile, held for the set dealer | pickups |
| Loose fill | the pickups on the free tiles before the ward | the ward's tier |

The door is read from the object's footprint in the catalog, the read-only reference every
part consults. The door is a shared value type that the filling and the guarding both
consult.

**The guarding**

| Concept | Owns | Never knows |
|---|---|---|
| Mouth guard tile | the cut tile where a guard seals the nook and fits, never a door | the filling |
| Guard level | the level drawn from the corpus spread at the place's hop | the buildings' worth |
| Guard rule | whether this nook's shape is guarded or left open | buildings |

**The kept ways**

| Concept | Owns | Never knows |
|---|---|---|
| Kept way | the promised mine ways, home ways and sea ways of one level | nooks |
| Start room | the walls and tiles around each player town | nooks |
| Home mine link | each town's walk to its own sawmill and ore pit | nooks |

**The record**

| Concept | Owns | Never knows |
|---|---|---|
| Nook decision | one line per nook: outcome, guard, ward and pickups | why |
| Nook paint | the tiles the overlay colours, the ones that got an object | the guard |

## 3. Invariants

1. No nook guard's zone of control covers a kept way or a start room, and none cuts a town
   off from its own sawmill or ore pit. Owner: the kept ways, which refuse the guard.
   Upheld by the mouth guard tile, which tries the next cut on a refusal.
2. No nook guard stands on a door. Owner: the mouth guard tile, which skips that cut.
3. No ward and no loose pickup stands on a door. Owner: the free tile. Added (log line 2).
4. A guard stands only after its ward stands, and every guarded nook holds one ward.
   Owner: the guarding, which rolls the nook back when the ward finds no free tile.
5. The same seed gives the same map. Owner: the guarding, which salts each nook's draw by its
   own cut tile.

## 4. Forces and patterns

Forces:

- F1. The nooks are one notion for every reader: the filling, the guarding and the seer
  huts. Two notions would drift and cost a second search.
- F2. The kept ways already serve six placement steps. A second copy would drift.
- F3. The run at 144 sits at about 70 s CPU, above the 57 to 60 s target met on 2026-10-10.

Patterns:

- Between parts: one pass per level, each nook handed along as a value. The kept ways stay
  a placement rule the guard's placement consults, as today (F2).
- The nooks are found once per level, with only the solid cells as obstacles, and every
  reader takes that one result (F1, F3). The finder costs the same with doors walkable
  (L2).
- Every concept is a plain function or a plain value. Nothing here varies.

Claims:

- Claims 1, 2: re-derived from F1 as the obstacle concept, which holds solid cells only.
- Claim 3: re-derived. The filling has one way of filling a nook, so a nook with buildings
  gets it unchanged.
- Claims 4, 5: re-derived from F2. The kept ways already hold the promised mine ways, the
  home ways and the sea ways. A neutral town inside a nook may be guarded. A player town
  sits in its start room, which the kept ways refuse.
- Claim 6: rejected by the user's claim 1.
- Claims 7, 8, 9, 10: kept.
- Claim 11: kept, on the new nooks (F1). The quests move on 2 maps (section 1).
- Claim 12: kept. The corpus family record counts a guard standing next to a door. A guard
  at a nook's mouth is rarely next to a building's door (A1).
- Claim 13: kept. The nook guard answers the nook's shape, not an effort gap.
- Claim 14: kept. The fairness loss at 72 is listed in section 1.

SOLID check: no role and no variant, so the check reduces to single responsibility. Each
Owns reads without "and".

Open lookups:

- L1. How many guarded nooks hold a building with the door-blind finder, and what moves.
- L2. The cost of finding nooks with doors walkable, at 144.
- L3. Whether a pickup or a guard can land on a door once doors lie inside nooks.

## 5. Mapping onto the existing system

Revision log:

1. Whole note, 2026-10-25: rewritten after the user's pushback. The contents part, the
   sealable rule, the prize role with its two variants, the second finding pass and the
   invariants that guarded today's cuts are gone. The user's claims 1 to 4 replace them.
2. Section 3, invariant 3, and section 2, the free tile: added. In the door-blind run on the
   verify maps, one loose pickup stood on a whirlpool's door (L3). Today no door lies in a
   nook, so the free tile never had to know doors.
3. Section 1, done-when: the verify nook moved from the Hut of the Magi alone (mouth 22,110)
   to the nook at mouth 20,103 that holds it with a second hut and a fountain. With doors
   walkable the three buildings share one nook.
4. Section 1, mine promise: today's count on seed 4 is two lines, a failed repair and the gap
   of 9 days, not one.

Lookups, measured on the eleven verify maps by a run of today's generator against one with
doors walkable in the finder:

- L1. Guarded nooks rise from 13.2 to 22.1 per 72 map, and from 48 to 78 at 144. Guarded
  nooks that hold a building's door rise from 10 to 105 over the ten 72 maps, and from 2 to
  33 at 144. At 144 the buildings inside are dwellings, banks, mines, spell buildings,
  temporary bonuses, permanent stat buildings, huts, mana wells, resource piles, and two
  neutral towns. 122 of today's 132 guarded nooks at 72 keep their mouth and guard tile, and
  46 of 48 at 144.
- L2. 103.1 s CPU against 101.7 s at 144, with six jobs in parallel. Peak memory 644 MB
  against 648 MB. The earlier per-call timing gave the finder 0.02 s more with doors
  walkable.
- L3. No guard stood on a door in either run. One loose pickup stood on a whirlpool's door in
  the door-blind run (log line 2). A Quest Gate's door held a pickup in both runs.

Parts:

| Part | Verdict | Where | Finding |
|---|---|---|---|
| The nooks | Reshape | `core/grid/pockets.py`, `loot/step.py:30-56,118-125` | doors are obstacles (`step.py:118,125`, `pockets.py:82`) |
| The filling | Reshape | `loot/pickups.py:411-500` | the free tile does not know doors |
| The guarding | Exists | `loot/pickups.py:375-386,503` | `_fill_planned` stands the ward, then the guard |
| The kept ways | Exists | `core/placement/ways.py`, `loot/pockets.py` | the home mine link lives in the loot pass, not in `kept_rules` |
| The record | Exists | `loot/result.py:38`, `cli/decisions.py:142`, `pickups.py:484` | none |

Concepts:

- Walkable land: Exists, the passable grid the loot step floods.
- Obstacle: Reshape. Today's obstacle is `access | occupied` (`step.py:125`), doors and
  solids mixed, and the mask matcher rejects a free mask cell on a door (`_matches` in
  `grid/pockets.py`). The design keeps `occupied` only. `find_pockets` gets no door set and
  `find_rooms` gets `occupied | loot`.
- Nook: Exists, the `Candidate` triple of cut, tiles and mouth.
- Nook shape: Exists, `pocket_kind` (`loot/pocket_plan.py:22`).
- Nook group: Exists, `dedupe_pockets` (`grid/pockets.py:149`).
- Door: Exists, `access_tiles` in `loot/pockets.py`, read from each object's footprint. It
  stays the `approach` set of `PocketContext`.
- Free tile: Reshape. `_spots` (`pickups.py:411`) and `_leaves_cache_spot` (`pickups.py:528`)
  filter claims, the placeable land and the cover. A whirlpool's door passed all three.
  Both gain `t not in self.approach`.
- Ward and loose fill: Exist, `_guarded` and `_unguarded` (`pickups.py:426,475`).
- Mouth guard tile: Exists, `_guard_fits` (`pickups.py:503`) refuses a tile in the approach
  set. The run confirmed 0 guards on a door.
- Guard level: Exists, `PrizeGuard.level`, salted by the cut tile (`pickups.py:398`).
- Guard rule: Exists, the deep test in `_fill_planned` (`pickups.py:378`).
- Kept way and start room: Exist, `WayRule` and `StartRoomRule` from `kept_rules`, fed by
  `PromisedWays` (`gameplay/result.py:135`).
- Home mine link: Exists as `home_mine_protect_pairs`, consulted in `_guard_fits`.
- Nook decision and nook paint: Exist. A guarded nook with buildings gets a ward, so the
  paint shows it.

What the code has that the design lacks:

- The seer huts read the deep nook tiles (`step.py:40-44`, `quests.py:86`). The design has
  them as a reader of the nooks (F1).
- The legacy path for zones without a plan (`_choose`, `_commit` at `pickups.py:602`)
  stands the guard before the ward, against invariant 4. Every nook decision on the verify
  maps is planned (A6). It reads the same nooks and the same free tiles, and keeps its order.

Claims against the code:

- Claims 1 to 3: the code follows none of them. The design adds them in the obstacle and
  the free tile.
- Claims 4, 5: the code holds the promised ways in `WayRule` and the home mine link in the
  loot pass. The design reuses both.
- Claim 6: the code follows it at `step.py:118-125` and `pockets.py:82`. The design drops it.
- Claims 7 to 11: the code follows them. The design keeps them.
- Claim 12: the code reads a family guard only next to a door (`reading/families.py`
  `door_guard`). A mine reads no guard at all (`reach_guard`). The design keeps both (A1).
- Claim 13: the design adds no guard for effort.

## 5b. What must not move

Before-values come from seeds 1 to 10 at 72 with 4 players free for all, and seed 15 at 144
with 4 players in 2v2, all with topology water. The after column is the door-blind run that
the slice must reproduce.

| Receiver | Gets today | Enforced by | Before | Holds when |
|---|---|---|---|---|
| Players at a guarded cache | today's guarded nooks keep their mouth and guard | nothing | 132 at 72, 48 at 144 | 122 or more kept at 72, 46 or more at 144 (run: 122, 46) |
| The set dealer | one held ward per guarded nook | invariant 4 | 132 at 72, 48 at 144 | equal to the guarded count (run: 221, 78) |
| Players collecting nook pickups | loose pickups in nooks | nothing; shallow loss out of scope | shallow 1070, deep 700 at 72; 316, 240 at 144 | total not below today on any map (run: 886 + 1190, 278 + 384) |
| Seer hut quests | an artifact in a deep nook | nothing; the move is out of scope | 8 quests at 72, 3 at 144 | 7 to 9 at 72, 3 at 144 (run: 8, 3) |
| Players promised a mine | every basic mine within 14 days | the mine-promise warning | two lines on seed 4, none elsewhere | the same lines |
| Every player's fairness | value claimed first against the best player's, within 5, 10, 20 and 40 days | nothing; the loss is out of scope | 0.408, 0.347, 0.414, 0.426 at 72; 0.976, 0.744, 0.682, 0.684 at 144 | within 0.02 of the run: 0.399, 0.314, 0.358, 0.422 at 72; 0.820, 0.636, 0.557, 0.581 at 144 |
| Players crossing the map | today's guard count | nothing | 62.2 per 72 map, 176 at 144 | rises by the new guarded nooks only (run: 71.1, 206) |
| Players visiting buildings | doors free of guards and pickups | invariants 2, 3 | 0 guards on a door, 1 Quest Gate door with a pickup | 0 guards and 0 new pickups on a door |
| Players at a gold mine | each gold mine contested at 144 | nothing | 0 uncontested | 1 or fewer (run: 1) |
| The user at 144 | the run's time and memory | nothing (A5) | 70.1 s CPU alone, 648 MB | 72 s CPU alone or less, 660 MB or less |
| The golden maps | fixed hashes per seed | the golden test | today's `data/golden.json` | regenerated in the same change, and two runs of one seed match |

## 6. Slices

1. **A nook with buildings is a nook.** Touches the obstacle (doors walkable in both
   finders), the free tile (doors refused) and the golden hashes. Done when: on seed 15 at
   144 the nook with mouth 20,103 shows a guard at 20,103 and a ward inside on the overlay,
   and its decision line says guarded. 8 to 17 guarded nooks per 72 map hold a building's
   door, and 30 to 36 at 144. Every 5b row is re-measured on the same eleven maps, before
   and after, and `make check` passes.

One slice is the whole change. The free-tile refusal cannot ship apart from the obstacle,
since it guards against a case only the new obstacle creates.

## 7. Assumptions

1. **Assumption**: on corpus maps a guard at a nook's mouth is rarely counted as the guard
   of the building inside, so the family guard record does not already price these guards.
   **Decided**: the nook guard is added on top of the family draw (claim 12 kept).
   **Basis**: the family reading counts a guard only next to a door (`reading/families.py`
   `door_guard`), and a mine counts no guard (`reach_guard`). **If wrong**: the guard rule
   (2) and the guard count row (5b).
2. **Assumption**: a guard in front of a mine that no player was promised breaks no
   promise. **Decided**: mines may sit in a guarded nook. **Basis**: `WayRule` keeps every
   promised mine way, and the run kept the mine-promise lines unchanged. **If wrong**: the
   kept ways (2).
3. **Assumption**: the user accepts the fairness loss at 72 for the coverage gain, under the
   rule that coverage and the full plan come before fairness. **Decided**: no fairness
   design here. **Basis**: claim 14, and the 144 readings move toward the corpus. **If
   wrong**: a follow-up on which nooks a guard may take, not on the nooks (claim 13).
4. **Assumption**: the nook at mouth 20,103 on today's default map stands for the case the
   user saw at 0,97. **Decided**: the slice verifies on it. **Basis**: the user's map
   generated on 2026-10-25 at 21:33 has water at 0,97, and the School nook appears only
   with `--water none`. **If wrong**: section 1's done-when and the slice (6).
5. **Assumption**: the run at 144 may spend 2 s more. **Decided**: one finding pass,
   with no saving sought. **Basis**: the door-blind run cost 1.4 s more under parallel load,
   and the finder 0.02 s more alone. **If wrong**: the finder (2).
6. **Assumption**: every zone on the verify maps has a zone plan. **Decided**: the legacy
   path keeps its guard-first order. **Basis**: every nook decision on the eleven maps is
   planned. **If wrong**: the legacy path needs the ward-first order (invariant 4).
7. **Assumption**: the corpus random-guard spread at the place's hop is the right level for
   a guard in front of buildings. **Decided**: the guard level is drawn as for every nook.
   **Basis**: the user's answer "same as any nook", 2026-10-25. **If wrong**: the guard
   level (2), invariant 5.
8. **Assumption**: a deep nook whose tiles are all doors or claimed stays open. **Decided**:
   it records the outcome it records today, with no guard. **Basis**: the guarded nook needs
   a free tile for its ward (invariant 4), and the run shows such nooks as empty, 14 to 23
   per 72 map. **If wrong**: a guard with no ward, and invariant 4.
9. **Assumption**: the measured counts hold for the shipped code. **Decided**: the slice
   uses them as ranges. **Basis**: the run patched the two finders exactly as the design
   says and left the free tile unchanged, which differs on one pickup. **If wrong**: the
   done-when ranges (6).
