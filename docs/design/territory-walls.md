# Territory walls grown as forest

Status 2026-10-18: proposed, not approved.

Disclosure: I read the vegetation samplers, the zone canvas, the border seal, the road web
and the wall widths before this skill loaded, while diagnosing seed 1029 at 144. The
request itself names a design. Every design decision either source carries is a claim in
1b.

## 1. Problem

A player on a large map meets the edge between two territories as a field of stumps, logs
and flowers in rows with gaps between them, where a hand-made map shows a forest or a
ridge. On seed 1029 at 144, the land around 95,25 holds 73 single-tile patch-up pieces
beside 44 single-tile pieces of real vegetation. Map-wide, the patch-up places 1201
single-tile pieces. The vegetation itself grows 1442.

Done looks like this to that player:

- The wall between two territories reads as the same trees and mountains as the land
  around it. The share of single-tile pieces among all decoration falls inside the
  corpus p10 to p90 for the map's size: 0.196 to 0.387 at 144, 0.171 to 0.412 at 72.
  Today seed 1029 at 144 gives 0.443. Seeds 1, 2 and 3 at 72 give 0.301, 0.446 and 0.392.
- The patch-up places at most a tenth of the pieces it places today on seed 1029 at 144,
  so at most 120.
- The walls keep their planned width. No more thin spots stay open between two walled
  territories than today.

Out of scope:

- The wall widths themselves, which keep their rule by door hops and map side.
- Walls the terrain step turns into water.
- The density and shape of vegetation inside a zone, away from its walls.
- The number and spacing of neutral towns, parked from the same investigation.
- The second sampler's look. It gets the wall through the same brief, and nothing here
  measures it (A8).

## 1b. Claims

1. The wall is planned once per level, before anything grows. (Request.)
2. Each zone's sampler gets its share of the wall as tiles it must cover. (Request.)
3. A piece may stand across the zone line, with its blocking cells in the neighbour's part
   of the same wall. (Request.)
4. Growth stays zone by zone. A level-wide sampler is not built. (My earlier reply.)
5. A pass after growth closes what growth left open with single-tile pieces. (Code.)
6. Each side of a wall gives up half its width, rounded up. (The water fronts do this.)
7. The width comes from the door hops between the two territories and the map side.
   (Commit 283dedd.)
8. The road web of a zone keeps off the one-tile rim only. (Code.)

## 2. Parts and concepts

### Level 1: parts

1. **Wall layout.** It decides which land tiles form the wall between two territories and
   which zone gives up each tile. It owns the geometry. It never knows a decoration or a
   road. It hands each zone its own part of each wall and its neighbours' parts facing it.
2. **Way through.** It plans the network of walkable tiles each zone keeps open, from its
   entrances to its middle. It keeps that network off the zone's part of every wall. It
   never knows a decoration.
3. **Growing.** It covers each zone's ground with trees and rocks at the corpus density and
   covers the zone's part of every wall outright. A piece may reach into the neighbour's
   part of the same wall. It never knows how the wall was derived, only its tiles.
4. **Closing.** Once everything has grown, it finds every crossing and every thin spot left
   between two walled territories and closes it. It never knows how growth went, only
   which tiles are open.
5. **Open ground.** It records, per zone, the tiles that stay walkable once growing and
   closing are done, whichever zone's piece blocks a tile. Later steps place everything
   on it.

Flow, per level: the layout acts first. Way through plans each zone's network around it.
Growing runs zone by zone, and each zone sees what the zones before it blocked. Closing runs
once after growing. Open ground is read after closing.

### Level 2: concepts

**Wall layout**

| Concept | Owns | Never knows |
|---|---|---|
| Wall width | The tiles a wall takes between two zones of different territories. Read-only input from the territory plan. | How walls are covered |
| Fixed openings | The tiles a wall never takes because the map needs them open: entrance bands, doors, landings, gate rooms. Read-only input. | Why each one is open |
| Wall share | The tiles of one zone within half the width, rounded up, of a walled neighbour, or within the full width of a fixed opening of that neighbour. | Decorations, roads |

**Way through**

| Concept | Owns | Never knows |
|---|---|---|
| Web route | The walkable network of one zone, off its wall share where any route exists. | The wall rule |

**Growing**

| Concept | Owns | Never knows |
|---|---|---|
| Forced cover | The tiles of a zone a sampler must block: the rim and the zone's wall share, less the web and the fixed openings. | The cellular field, the identities |
| Overhang | The tiles outside a zone where a blocking cell of its pieces may stand: the neighbours' wall shares facing it. | Which neighbour grows first |
| Standing cover | The tiles already blocked when a zone grows, counted as covered. | Which zone blocked them |
| Sampler | One zone's pieces, covering the forced cover. Existing role with two variants. | The wall layout |

**Closing**

| Concept | Owns | Never knows |
|---|---|---|
| Leak | A pair of open tiles of two zones closer than their wall allows, or touching across a closed border. | How it arose |
| Patch piece | One single-tile blocking piece closing a leak, drawn by terrain. | The sampler |

**Open ground**

| Concept | Owns | Never knows |
|---|---|---|
| Open ground | A zone's tiles minus every tile any piece on the level blocks. | Which piece blocks it |

Wall width and fixed openings are read-only inputs that Wall layout and Closing both read.
Neither part owns them.

## 3. Invariants

- **I1. A wall keeps its width.** No two open tiles of walled zones stand closer than the
  width, unless both are fixed openings or web. Owner: Closing, which finds every leak.
  Wall layout, Way through and Growing uphold it. Today Closing gives up on a leak it cannot
  close without walling off ground and says nothing. The design keeps that, and 5b counts
  the leaks left.
- **I2. Fixed openings and the web stay open to growth.** No sampler piece blocks them.
  Owner: the zone canvas legality check, which refuses the piece. Closing may still thin
  the web where the web stays joined, as today.
- **I3. A piece reaches out only into its overhang.** Owner: the canvas legality check.
- **I4. No open ground is walled off.** Owner: the level check after closing, which fails
  the step. The canvas and Closing uphold it.
- **I5. Open ground holds no blocked tile.** Owner: Open ground, computed once per level
  from every piece on the level.
- **I6. The same seed gives the same walls.** Every draw comes from a seeded stream.
  Owner: the golden test.

## 4. Forces and patterns

Forces:

- **F1. The sampler varies.** Two samplers exist and the wall must reach both. So the wall
  travels in the brief every sampler already receives, as more forced tiles and an
  overhang. No sampler learns about walls.
- **F2. Width varies by pair and by map side.** The geometry does not depend on the
  decoration. So the wall share is a plain function of the zone grid, the widths and the
  fixed openings.
- **F3. The road web and the wall want the same tiles.** On seed 1029 at 144, 1049 of the
  wall's 10431 tiles are web and nothing else. No sampler may plant on the web, so the
  patch-up thins it, 187 single tiles on level 0. So the wall must be known before the web
  is routed, and the web keeps off it.
- **F4. Fixed openings sit inside walls.** A door band of one zone faces the other zone at
  less than the wall width. Half per side alone leaves 1412 thin spots on level 0 of seed
  1029. Adding the tiles within the full width of a neighbour's fixed opening leaves 1001,
  and 994 of those have both tiles kept open. So the share holds both rules.
- **F5. Borders are jagged.** Half per side leaves a few thin spots at corners: 7 closable
  ones on level 0 of seed 1029 with the share fully covered. So the layout is approximate
  and Closing stays the exact pass. It only shrinks.
- **F6. Large pieces need room across the line.** A 6-tile wall split 3 and 3 fits a 2-wide
  tree on each side but cannot centre a 3-wide one on the line. So a piece may reach into
  the neighbour's share. This is the least certain force (A5), so its slice comes last.
- **F7. The run at 144 has little time to spare.** So the share comes from distance passes
  over the level grid, not one search per pair.
- **F8. Both territories lose land to the wall.** Splitting it evenly keeps either side
  from losing more.

Patterns:

- Between parts: one value handed along. The layout's shares join each zone's plan beside
  its rim. Way through, Growing and Closing read them. No new port: only the sampler
  varies, and it already has its role (F1).
- Inside Wall layout: a plain function (F2, F4, F7).
- Inside Way through: the wall share joins the tiles the route keeps off, with the existing
  fallback when no route avoids them (F3).
- Inside Growing: two more fields in the existing brief (F1), one legality rule more in the
  canvas (F6).
- Inside Closing: unchanged (F5).
- Inside Open ground: a plain set difference once per level (I5).

Claims: 1 from F3 and F7. 2 from F1. 3 from F6. 4 from F7 and the scope: a level-wide
sampler would rewrite both samplers. 5 from F5. 6 from F8, extended by F4. 7 stays out of
scope. 8 is rejected by F3.

SOLID: no new variant appears. The sampler role gains inputs its consumer already
supplies. Each concept's Owns reads as one set or one network.

Open lookups, each resolved in section 5 or measured:

- L1. How many thin spots half per side leaves once the shares are covered. Measured: F4
  and F5.
- L2. How much of each share is kept open, and by what. Measured: F3.
- L3. The step's time today, split between growing and closing. Measured: 5b.
- L4. The corpus share of single-tile pieces among decoration. Measured: section 1.
- L5. Whether the fixed openings are known before the web is routed. Resolved in section 5.

## 5. Mapping onto the existing system

Revision log:

- R1. Section 2, Wall share: was half per side alone. L1 left 1412 thin spots on seed 1029
  level 0, against 260 after today's patch-up. Added the full width around a neighbour's
  fixed opening (F4).
- R2. Section 2, part 2 Way through: new. L2 showed half of the wall's kept-open tiles are
  web only, and the patch-up's 187 web tiles on seed 1029 level 0 come from there (F3).
- R3. Section 2, Fixed openings: was "kept-open ground" with the web inside it. The web is
  now routed after the wall, so it cannot define the wall (L5).
- R4. Section 6: the overhang moved from the first slice to the last (F6, A5).
- R5. Section 6, S1: S1 alone raises the thin spots left on A from 260 to 386, nearly all
  web on both sides. S1 cannot ship without S2. See the S1 measurements.
- R6. Section 5, Sampler: the field sampler fills each target tile once in random order,
  and 734 share tiles on A level 0 failed only because of that order. Forced tiles need to
  fill from the zone edge inward. Sampler changes from Exists to Reshape.
- R7. Section 5b, thin spots: the row now counts only the thin spots farther than the wall
  width from a door or an entrance band. On A level 0, 255 of today's 260 sit at a door
  approach, where both sides' roads meet the door. After S2 all 372 do. Those are the
  roads into the door, not a leak.
- R8. Section 7, A1: wrong. S2 leaves 708 patch-up pieces on A level 0, not 120. The bare
  wall tiles left are web, bands and patch edges the sampler never tries (624), tiles
  where any piece would wall off ground behind it (556), and tiles no piece fits (153).
  Routing the web off the wall moved little more. The rest needs pieces that may cut a
  small pocket off, as the patch-up does, or the overhang.

### Parts

- **Wall layout: New.** `core/planning/borders.py`, beside `deep_pairs`, which already
  owns zone-border geometry and reads the same widths. The terrain step's water fronts
  carry the half-width rule for territory pairs (`terrain_gen/water.py:190` `front_of`).
  That is a second copy of one rule over another grid. It stays for this change (A7).
- **Way through: Reshape.** `planning/zone_plan.py:275` passes `keep_off=rim8` to
  `planning/web.py` `protected_web`. The web picks its nodes from the zone interior,
  `edist >= 2` (`web.py:126`), so a node can sit inside a 3-tile share and pull the route in.
  Both read the share.
- **Growing: Reshape.** `vegetation/grow.py:131` forces the rim less the entrance bands.
- **Closing: Exists.** `vegetation/border_plan.py` `seal_borders`. Its Owns and Never-knows
  match.
- **Open ground: Reshape.** `grow.py:144` takes only a zone's own blocked tiles off its open
  ground. A neighbour's overhang would stay counted as open. `step.py:214` removes the
  closed tiles per zone afterward, and that part matches.

### Concepts

- **Wall width: Exists.** `terrain_gen/territories.py:332` `wall_depths`, published on the
  place map per level and read by `vegetation/step.py:94` `_depths`.
- **Fixed openings: Exists, spread.** Entrance bands come from the passages, doors from the
  territories, landings and gate rooms from `step.py`. All are known before
  `step.py:189` builds the zone plan, which resolves L5. The home town rooms are chosen
  after the web, in `plan_player_zones`. They are left out of the rule (A6).
- **Wall share: New.** A function in `planning/borders.py` from the zone label grid, the
  widths and the fixed openings to each zone's share. `PlanZone` carries it beside `rim8`,
  because `PlanZone` already owns each zone's rim, bands and web.
- **Web route: Reshape.** `keep_off` becomes the rim plus the share. The node candidates
  leave the share out. `web.py:121` keeps its fallback to the full zone when no route
  avoids them.
- **Forced cover: Reshape.** `grow.py:131` adds the share to `border`. The field sampler
  forces `border` outright (`field/cellular.py` `target_mask`). The Gibbs sampler gives it
  a bonus (`gibbs/sampler.py:103`).
- **Overhang: New.** A field of `SampleOptions`. `ZoneCanvas.blocked_cells` refuses any
  blocking cell outside the zone (`canvas.py`, `not inz[ly, lx]`) and accepts one in the
  overhang instead. The window is the zone's box grown by the largest piece's reach plus
  one, so every overhang tile a piece can reach is inside it.
- **Standing cover: Reshape.** Earlier zones' blocked tiles reach the canvas as
  `impassable`, which only counts for connectivity. The field sampler's target and fill
  score read only the zone's own count, so a tile an earlier zone covered through its
  overhang would be covered twice. The canvas takes standing cover off the target and
  scores a cell on it as neither gain nor spill.
- **Sampler: Exists.** The `Sampler` role in `vegetation/sampler.py`.
- **Leak, Patch piece: Exist.** `deep_pairs`, `closing_pairs` and `_Decor` in
  `border_plan.py`. The seal never closes a band or an avoid tile and does close web tiles
  (`_Sealer.sealable`), which matches I2.
- **Open ground: Reshape.** As in the parts.

### What the existing system has that the design lacked

- **Ground patches.** A zone grows one run per patch of another terrain, each with its own
  `forbid` (`grow.py:115`). The design missed them. Each run forces the share inside its
  own tiles, as it forces the rim today. No new concept.
- **The cut-off budget.** Closing may shut up to four open tiles away with a leak
  (`MAX_CUT`). That is Closing's own business. No change.

### Claims against the code

| Claim | Code today | Design |
|---|---|---|
| 1 | No: the wall exists only as pairs Closing reads | Yes |
| 2 | No: only the rim is forced | Yes |
| 3 | No: `blocked_cells` refuses any cell outside the zone | Yes, last slice |
| 4 | Yes | Yes |
| 5 | Yes, and it builds most of the wall | Yes, for what is left |
| 6 | Water fronts only | Yes, with the fixed-opening rule |
| 7 | Yes | Unchanged |
| 8 | Yes | No |

## 5b. What must not move

The change moves which tiles the samplers must cover, where the web runs, where pieces may
stand, and what Closing has left to do. Before-values come from configs A (seed 1029 at 144,
4 players, 2v2, two levels, density 1.5) and B, C, D (seeds 1, 2, 3 at 72, 4 players), all
with the field sampler. A is split by level as L0 and L1.

| Receiver | Gets today | Enforced by | Before | Holds when |
|---|---|---|---|---|
| A hero between two walled territories | Thin spots left open after the patch-up, away from door approaches (R7) | nothing | A L0 5 of 260 | Each at or below today |
| A hero at a closed border | Walkable crossings left open | nothing | A 9 / 0, B 0, C 3, D 5 | Each at or below today |
| A player's room to move | Open land after vegetation | nothing | A 8380 / 2232, B 2441, C 1891, D 2150 | Each at least 90% of today (A3) |
| Every later step | No open pocket walled off | the level check after closing | passes on all | passes on all |
| Every later step | Open ground holds no blocked tile | nothing today, I5 after | holds, no piece crosses a zone | holds |
| A player waiting for a 144 map | Vegetation step time on A | the speed target in memory, by hand | 10.6 s, of which growing 10.0 and patch-up 1.5 on a first pass | At most 10% slower, best of three runs (A4) |
| Neutral town placement | Towns placed on seed 1029 at 144 | nothing | 21 | 21 |
| The golden maps | Same seed, same map | the golden test | current hashes | regenerated in the same change, every other check green |

## 6. Slices

**S1. The wall as forced cover.** Wall layout computes each zone's share. Growing forces it.
The web stays as it is. Touches Wall width, Fixed openings, Wall share, Forced cover. The
patch-up is expected to drop to about a fifth, because it still thins the web (A1). Done
when, on A to D, the single-tile share and the patch-up count are re-measured against
section 1, and every 5b row is re-measured inside its holds-when.

S1 measured on 2026-10-18, built but not committed. It fails its 5b rows.

| Measure | A L0 | B | C | D |
|---|---|---|---|---|
| Patch-up pieces | 1196 to 979 | 44 to 34 | 92 to 81 | 96 to 71 |
| Thin spots left | 260 to 386 | 1 to 0 | 9 to 9 | 12 to 0 |
| Open land | 8380 to 8305 | 2441 to 2442 | 1891 to 1871 | 2150 to 2151 |
| Single-tile share, full run | 0.469 to 0.436 | 0.348 to 0.346 | 0.483 to 0.462 | 0.427 to 0.413 |

- The thin spots left on A rise. 381 of the 386 have a kept-open tile on both sides, and
  337 have web on both sides. Denser walls make more web tiles the only way through, so
  the patch-up can no longer thin them. S1 needs S2 to show any gain at 144.
- The sampler leaves 1606 share tiles bare on A level 0. 741 are web. 734 failed because
  blocking them would have walled off a tile behind them. The sampler tries each target
  tile once in random order, so a tile filled before the tiles behind it is refused for
  good.
- A second pass over the bare forced tiles cuts the patch-up on A to 516 and costs about
  half the step's time again. Filling the forced tiles from the zone edge inward cuts it to
  764, with no second pass. Both timings come from a machine at load 20, so neither is
  settled (A4).
- Three downstream tests fail on seed drift: two compensation tests and the mine promise
  on seed 8 at 48, a 6-day gap on a sulfur dune.

**S2. The web routed off the wall.** Way through keeps the route and its nodes off the
share. Touches Web route. Done when the patch-up count on A is at most 120, the single-tile
share sits inside the corpus range on A to D, and every 5b row holds.

S2 measured on 2026-10-18 with S1 and the edge-inward fill order, built but not committed.
It holds every 5b row and misses its own target.

| Measure | A L0 | A L1 | B | C | D |
|---|---|---|---|---|---|
| Patch-up pieces | 1196 to 708 | 5 to 3 | 44 to 44 | 92 to 49 | 96 to 61 |
| Thin spots left, all | 260 to 372 | 2 to 4 | 1 to 0 | 9 to 9 | 12 to 0 |
| Thin spots away from doors | 5 to 0 | 0 to 0 | not split | not split | not split |
| Crossings left | 9 to 14 | 0 to 0 | 0 to 0 | 3 to 4 | 5 to 5 |
| Open land | 8380 to 8130 | 2232 to 2208 | 2441 to 2389 | 1891 to 1843 | 2150 to 2121 |
| Single-tile share, full run | 0.469 to 0.406 | both levels | 0.348 to 0.356 | 0.483 to 0.450 | 0.427 to 0.412 |
| Neutral towns | 17 to 17 | | 4 to 4 | 2 to 2 | 3 to 3 |

- The step time on A holds: best of the paired runs 9.6 s before, 10.0 s after, with the
  rounds overlapping.
- The lint, the tests, the golden maps, the readings sweep over seeds 1 to 10 at 72 and full
  runs of seeds 25 and 1029 at 144 pass. The three tests that failed under S1 pass.
- The crossings left on A level 0 rise from 9 to 14 and on C from 3 to 4. Each sits at a
  door approach.
- The patch-up target of 120 is missed (R8). The single-tile share stays above the corpus
  p90 at 144 on A (0.406 against 0.387) and above the corpus p90 on C (0.450 against 0.412).
  Without the patch-up pieces, A's share would be about 0.325.

**S3. Pieces across the line.** Only when S2 leaves the single-tile share above the corpus
p90 on any of A to D. Touches Overhang, Standing cover, Open ground. Done when the S2
measures hold and no open-ground tile is blocked on any level of A to D.

Each slice regenerates the golden hashes and updates the vegetation and planning `AGENTS.md`
maps and `docs/design/vegetation-sampler.md` in the same change.

## 7. Assumptions

1. **A1. Covering the share and routing the web off it leaves the patch-up under a tenth.**
   Decided: S2's done-when is 120 pieces on A. Basis: with the share covered, level 0 of A
   keeps 20 crossings and 7 closable thin spots. The other 994 thin spots have both tiles
   kept open, and about half the kept-open wall tiles are web only. Today the patch-up
   closes 187 web tiles there. If wrong: F3, Way through, S2's done-when. Found wrong on
   2026-10-18 (R8).
2. **A2. The web finds a route off the share in most zones.** Decided: the web keeps off the
   share with the existing fallback to the full zone. Basis: `web.py:121` already falls
   back when the rim blocks a route. None for how often the share blocks one. If wrong:
   Web route, I1's exception, A1.
3. **A3. Open land falls by at most a tenth.** Decided: the 5b holds-when. Basis: on level 0
   of A, 1548 share tiles are neither kept open nor covered after growth, against the 957
   the patch-up closes in the wall today. About 600 more tiles close, 7% of 8380. Routing
   the web off the share frees more tiles to cover. If wrong: Wall share rule, F4.
4. **A4. Forcing the share costs at most a tenth of the step's time.** Decided: the 5b
   holds-when. Basis: the share adds about 1548 target tiles to 11160 already covered on
   level 0 of A, and the patch-up's 1.5 s shrinks. The timings vary between runs: the
   first pass of A took 18.5 s in all, the last 12.9 s. If wrong: F7, the slices' order.
5. **A5. Trees fit a 3-tile share at 144 and a 2-tile share at 72 without crossing the
   line.** Decided: the overhang is the last slice and may never be built. Basis: none.
   If wrong: S3 becomes needed, Standing cover and Open ground with it.
6. **A6. Home town rooms stay clear of walls without a rule.** Decided: the share leaves
   them out, and Closing keeps handling any leak next to one. Basis: home towns sit in the
   zone's middle. None measured. If wrong: Fixed openings, and the home planning order.
7. **A7. The water fronts' copy of the half-width rule stays separate.** Decided: no shared
   function in this change. Basis: the fronts grow over territory labels in the terrain
   step, the share over zone tiles in vegetation. If wrong: a shared rule in
   `planning/borders.py`, owned by `target-architecture`.
8. **A8. The Gibbs sampler takes the share as a bonus, not a must, and nothing measures
   it.** Decided: out of scope. Basis: `gibbs/sampler.py:103`. If wrong: Gibbs maps keep
   their patch-up, and a slice for them follows.
