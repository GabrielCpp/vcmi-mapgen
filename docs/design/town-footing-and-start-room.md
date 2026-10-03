# Town footing and the start room

Disclosure: I read the study's working patch (`variants_t.py`, arm t6) before this skill
loaded, and the session context lists the repo's modules. Every design decision that patch
carries is a claim in 1b, and section 4 re-derives or rejects each one.

## 1. Problem

A player opening a generated map sometimes finds their starting town boxed in. A monster
stands in front of the gate, or a guard or a solid object closes the few tiles around it, so
the first day starts with a fight or a dead end. Neutral towns are also scarcer than on a
hand-made map, because a town today needs its whole body inside its zone, clear of trees,
two tiles from every other building and off the zone's entrance strips.

Done looks like this to that player:

- No player start has a monster whose zone of control touches the town's entrance tile.
- No guard and no solid object leaves a hero fewer than 12 tiles to walk from the entrance,
  unless that room was already smaller before the object came.
- A town stands wherever its entrance tile is free, walkable and reachable from the zone's
  paths. Its body may overlap trees and may spill past the zone edge onto land a hero cannot
  walk, never onto water or rock. On the study's 67 bench maps that gave 483 towns against
  453.

Out of scope:

- The look of the map. The study measured that this change does not move it.
- Global reachability between players. The start room is a local guarantee.
- Vegetation spilling across zone edges. That is the study's next lever.
- Mine placement, which keeps its own guard and seal rules.

## 1b. Claims

From the study patch, arm t6:

1. Every town, player or neutral, may anchor anywhere its footprint touches the zone, so the
   body can leave the zone.
2. A body cell outside the zone must be in bounds, unwalkable and not water or rock.
3. A town drops the two-tile gap to other gameplay bodies.
4. A town drops the entrance strips and the underground tunnels from its forbidden cells, and
   keeps earlier approach tiles and the avoid set.
5. A town keeps the approach rules: in the zone, free, walkable, reachable, doors walkable, no
   stranded tile.
6. A player town's entrance tile is registered when the town is placed, moved, or promoted to
   player at the end.
7. A guard is refused when its zone of control covers a registered entrance, or when the room
   reachable from that entrance, 8-connected, outside every zone of control, drops below 12
   tiles and below what it was without the guard.
8. Every object except pickups, heroes, guards and towns is refused by the same test, with its
   blocking and interactive cells in place of a zone of control.
9. Only entrances within 13 tiles of the candidate are tested.
10. The rule hooks the one tile-cover check every placement consults, so every later step
    obeys it without knowing it.

## 2. Parts and concepts

### Level 1

1. **Town siting** decides where a town stands in its zone. It owns which anchors are legal
   for a town and which one wins. It never knows about player starts or later objects. It
   hands a placed town to start registration.
2. **Start registration** knows which towns are player starts. It owns the list of protected
   entrances on each level. It never knows how a spot is chosen. It hands that list to the
   start room guard, once while gameplay places towns and again from the finished map for
   every later placer.
3. **Start room guard** answers one question for any candidate object: does it take a
   player's entrance or shrink their room? It owns the room test. It never knows which step
   asks or why.
4. **Tile cover** is the existing record of what covers each tile and which placements clash.
   It owns the yes or no every placer asks before placing. It never knows what a start is. It
   consults whatever rules it was given.

Flow: town siting places a town. When the town is a player start, start registration adds
its entrance. From then on every placer asks tile cover, tile cover asks the start room
guard, and a refusal makes the placer try its next candidate. At the end of gameplay the
finished map's player towns become the list every later step builds its guard from.

Plain paragraph: the generator picks a spot for each town and only cares that a hero can
reach the gate. It writes down which towns belong to players. Before anything else is put on
the map, a checker asks whether the new thing would stand on a player's doorstep or close
them in, and says no when it would.

### Level 2

**Town siting**

| Concept | Owns | Never knows |
|---|---|---|
| Footing (role) | which anchors to try and whether one is legal for an object's body | how spots are scored |
| Zone footing (variant) | the body inside the zone, gap kept, off strips, tunnels and approaches | towns |
| Town footing (variant) | the body off other bodies and approaches, each cell in the zone or on spillable land | the gap and the strips |
| Spillable land | a tile outside the zone a body may cover: in bounds, unwalkable, not water or rock | footings |
| Spot choice | the best legal anchor near each centre by back contact | which footing produced the anchors |

**Start registration**

| Concept | Owns | Never knows |
|---|---|---|
| Start entrance | a player town's entrance tile and level, a value | the town's footing |
| Start list | the entrances protected on one level, growing as player towns are placed | the room test |

**Start room guard**

| Concept | Owns | Never knows |
|---|---|---|
| Zone of control | the tiles a guard threatens: its interactive cells and their 8 neighbours | starts |
| Passable tile | whether a hero may stand on a tile: in bounds, not gate-blocked, not water or rock, no blocking or interactive cover except pickups and heroes | rooms |
| Start room | the count of tiles reachable from an entrance outside every threatened or walled tile, capped at 12 | which object asked |
| Start room rule (variant of placement rule) | the refusal of a guard or a solid object that takes an entrance or shrinks its room | which step places |

**Tile cover**

| Concept | Owns | Never knows |
|---|---|---|
| Clash | the existing refusal of a cell on another object's door | starts |
| Placement rule (role) | a reason a candidate may not stand where it is, given the covers | the rule's variants |

Shared value types: start entrance, footprint, tile. Shared read-only reference: the terrain
grid of the level.

## 3. Invariants

1. A placed player town's entrance tile is never inside a guard's zone of control. Owner:
   start room rule. Upheld by every placer that asks tile cover.
2. A placement never drops a start room below 12 tiles when it was 12 or more without it.
   Owner: start room rule.
3. A town's body covers no water or rock tile and no other gameplay body. Owner: town
   footing.
4. A town's entrance is reachable from its zone's paths and the town strands no tile. Owner:
   zone site commit, unchanged.
5. Tile cover never accepts a candidate a rule refuses. Owner: tile cover.

## 4. Forces and patterns

Forces:

- F1. Every later step places guards and solid objects, and none of them may need to know
  about starts. About ten placers build their own cover record.
- F2. The start test needs the level's terrain and gate tiles, which the cover record does
  not hold, and a bounded search, which the model package may not hold.
- F3. Towns and the other gameplay objects have two different body rules, chosen by purpose.
- F4. Unit tests must check the room test and the town footing on a few literal tiles.
- F5. Determinism: same seed, same map.

Patterns:

- Between parts, **a rule handed to tile cover** (F1, F2). Tile cover takes a sequence of
  placement rules at construction and asks each in its conflict check. The role is declared
  beside tile cover. The start room rule lives in placement, so the model never searches.
  This re-derives claim 10 from F1. A global hook is rejected, because it is hidden state.
- Each later step builds its rules from the finished map, because the player towns, the
  terrain and the gate tiles are map facts. No new registry value is needed (F1).
- Inside gameplay, the start list grows. The level's shared field owns one start room rule
  and the step adds each player town's entrance to it after placing it (claim 6, partly, see
  A2).
- Inside town siting, **footing as a strategy** (F3). Zone footing is the existing fit,
  unchanged. Town footing is the second variant. The zone site picks the footing by purpose,
  in one table. Claims 1 to 5 are re-derived from premises 15 and 17 and from F3.
- Start room and passable tile are plain functions over literal sets (F4).
- Claims 7, 8 and 9 are re-derived from premise 16 and the seed 9009 seal. Claim 9 is a
  cheap bound: a room capped at 12 cannot reach a candidate more than 13 tiles away.

SOLID check: each Owns reads without "and". A third footing adds one class and one table
row. Town footing is a kind of footing only. The placement rule declares one method. Tile
cover's Never-knows names starts.

Open lookups:

- L1. Does the mine flag in the existing fit fit the footing role? Decides whether mine is a
  third variant now.
- L2. Which call sites build a cover record after gameplay, and do they hold the map?
- L3. Is `add_objs(new, rules)` in `core/model/AGENTS.md` a past design or a stale line?

## 5. Mapping onto the existing system

Revision log:

- R1, section 4, footing: the mine flag stays a parameter of zone footing. Moving mines is out
  of scope (L1, A4).

Parts:

- Town siting: **Reshape**, `core/placement/site.py`. `ZoneSite.place` tries `sorted(self.ts)`
  and calls `self.fit` for every purpose (site.py:368). The anchor list and the fit become
  the footing's job.
- Start registration: **New**, `core/placement/start_room.py` holds `StartRoomRule` with
  `protect(town)`. `GameplayStep` adds each placed player town (step.py `place_town`,
  `_move_player_towns`).
- Start room guard: **New**, same module. `guards.py` already owns `guard_zoc`, the zone of
  control over a list of objects. The rule reuses its neighbourhood definition.
- Tile cover: **Reshape**, `core/model/map_state.py` `CoverIndex`. It gains `rules` and a
  `covers_at(tile)` read. `MapState.add_objs` stays as it is, because placers never rely on
  its refusal.

Concepts:

- Zone footing: **Exists** as `ZoneSite.fit` and `guards.fits`. Owns and never-knows match.
- Town footing: **New** in `site.py`.
- Spillable land: **New** as a function in `site.py`. `LevelField` keeps `unwalkable` but not
  the barrier set alone. It gains `barrier`, filled in `LevelField.build` from the same grid
  scan.
- Spot choice: **Exists**, the neighbourhood loop in `ZoneSite.place`.
- Start entrance and start list: **New**, inside `StartRoomRule`.
- Zone of control: **Exists**, `guards.guard_zoc`.
- Passable tile, start room, start room rule: **New**.
- Clash: **Exists**, `_clash` in `map_state.py`.
- Placement rule: **New**, a `Protocol` in `map_state.py` beside `CoverIndex`.

Call sites (L2). Cover records built after gameplay: `border/crossings.py:46`,
`border/entrances.py:44`, `gated/placer.py:263`, `treasure/fill.py:247`,
`loot/step.py:101`, `loot/quests.py:71`, `loot/pickups.py:163`, `scatter/piles.py:53`,
`portal/step.py:97`, `placement/scatter.py:102`, `placement/water.py:102`. Each runs inside
a step whose `run` has the map. The steps build the rule with
`start_rules(map_state, level)` and pass it to their cover record. A record that only
probes a guard against itself (`pickups.py:325`) needs none. `vegetation/border_plan.py`
runs before any town exists and needs none.

Mismatches:

- M1. `core/model/AGENTS.md` says every step writes through `add_objs(new, rules)`. The code
  takes no rules (map_state.py:269). The doc is stale (L3). The doc changes to say the cover
  record takes the rules.
- M2. `GameplayStep._player_towns` may promote a neutral town ahead of a moved player town
  (step.py:335). The study protected the moved town during gameplay and the promoted one
  after. The port protects whatever the finished map calls a player town, and protects moved
  towns during gameplay as the study did (A2).
- M3. `ZoneSite.add_guard` adds a mine guard without asking cover (site.py:412). The mine fit
  probes the guard tile first with `guard_ok`, so the rule still applies. No change.

What the existing system has that the design lacks: the shared field's `near` set and
`reserved` strips, which zone footing keeps. Not waste. Zone footing owns them.

Claims: the existing system follows claims 5 and 10's choke point already. The design adopts
1 to 10, with 10 made explicit as constructor rules instead of a global hook.

## 6. Slices

1. **Start room on every placer.** Placement rule role, `StartRoomRule`, the cover record's
   `rules`, gameplay registering player towns, every later step passing the rule. Done when
   no seed among 1 to 20 at sizes 48 and 72 has a guard's zone of control on a player
   entrance or a start room under 12 tiles, measured with the study's own counters, and unit
   tests cover the room test on literal grids.
2. **Town footing.** Footing role, town footing, spillable land, the barrier set on the
   shared field. Done when the ported main reproduces the study patch byte for byte on seeds
   1 to 10 at size 72 with players, run in the study worktree with only the t6 patches over
   the same commit, and `make check` passes with the golden hashes regenerated.
3. **Docs.** `core/model/AGENTS.md`, the `site.py` module docstring and the gameplay step
   docstring say what the code does.

## 7. Assumptions

1. **Assumption**: the study's t6 patches, applied alone over main's commit, are the reference
   the port must match. **Decided**: slice 2 proves byte equality against that run, not
   against the study's arm, which also carries other study changes. **Basis**: the arm's
   overrides list the extra entries apart (`logs/t6.overrides.json`). **If wrong**: section 6
   slice 2.
2. **Assumption**: protecting the finished map's player towns plus every town gameplay placed
   for a player zone matches the study on the bench. **Decided**: registration as in M2.
   **Basis**: the study registered the same towns. **If wrong**: start registration.
3. **Assumption**: a bounded room search per candidate near a start costs under a second per
   map. **Decided**: no cache. **Basis**: t6 ran the whole bench at the same pace as t5 in the
   study log. **If wrong**: start room rule, pattern section 4.
4. **Assumption**: mines keep their own fit and flag. **Decided**: zone footing carries the
   mine flag. **Basis**: the request names towns, guards and walls only. **If wrong**: footing.
5. **Assumption**: the golden hashes change and the user accepts the new maps.
   **Decided**: slice 2 runs `make golden`. **Basis**: the user asked for the port. **If
   wrong**: none, the port stops.
