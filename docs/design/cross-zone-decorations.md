# Decorations that cross zone borders

Disclosure: I read the vegetation code before writing this note: the zone canvas, the
connectivity check, the field sampler, the level grower and the island check. Its design
decisions are listed as claims in 1b and are re-derived or rejected in section 4.

## 1. Problem

Players on small maps see thin strips of land dotted with lone bushes and rocks. In the
corpus, big trees and mountains wall the strip edges and sit across terrain borders. Our
vegetation keeps every blocking cell of a decoration inside the zone that grows it. A strip
has a zone border on both sides, so big pieces rarely fit and lone pieces fill the gap.

Measured at size 36 against the 31 corpus maps of that size or smaller:

| | corpus | ours |
|---|---|---|
| big decorations straddling two zones | 12% | 1% |
| lone pieces per 100 tiles of thin strip | 8.4 | 13.1 |
| share of decorations that are lone | 29% | 55% |
| thin strip land covered | 57% | 43% |

Done looks like this on a 90-map sweep (sizes 36, 72 and 108):

- Big decorations straddle two zones at about the corpus rate, 8% to 15%.
- Lone pieces in thin strips fall to 10 per 100 tiles or fewer.
- Every map still generates. No open land is walled off. Every path, entrance band, town room,
  sea landing and door stays clear.
- Starting towns miss their sawmill or ore pit no more often than today.
- Size 144 stays within the speed target, 60 s of CPU.

Out of scope: decorations on water or rock (6% of corpus big pieces touch one), which cells
the border closing picks, the Gibbs sampler's tuning, sawmill siting and the depleted zones.

## 1b. Claims

1. Vegetation grows zone by zone, each zone with its own terrain's model and mix (grower).
2. A decoration's blocking cell is legal only inside the zone that grows it (zone canvas).
3. The walkability check sees one zone's bounding box and treats every tile outside the zone
   as a wall (zone canvas).
4. A decoration's anchor tile lies inside the zone (field sampler).
5. The field sampler tries one random position per drawn decoration (field sampler).
6. The field sampler ranks candidates by target tiles covered minus off-target tiles covered
   (field sampler).
7. A zone's open and walkable tiles are its tiles minus what it grew itself (grower).
8. A level-wide check after growth fails the map on any walled-off pocket (vegetation step).
9. The border closing seals a path tile only when its open neighbours in its own zone stay
   joined inside that zone (border closing).

## 2. Parts and concepts

### Level 1

1. **Ground rules** decide whether a decoration's blocking cell may stand on a tile. They own
   the level's reserved tiles and the terrain under each tile. They never know zones' mixes or
   walkability. They answer the zone dresser and the walkability guard.
2. **Walkability guard** keeps every open land tile joined to the walkable network while
   decorations go down. It owns the level's blocked and open state. It never knows which
   decoration or which zone. It answers the zone dresser.
3. **Zone dresser** covers one zone's coverage target with decorations drawn from that zone's
   corpus mix. It owns the zone's target and mix. It never knows another zone's mix or target.
   It hands each placement to the walkability guard.
4. **Growing order** walks the zones in a fixed order and hands each zone dresser the level as
   the earlier zones left it. It owns order and determinism.
5. **Zone ledger** gives each zone its open and walkable tiles once the whole level has grown.
   It owns the per-zone view the later steps read.
6. **Border closing** shuts the open crossings between zones that no entrance plans, with lone
   pieces, after the whole level has grown. It owns which crossings stay open. It never knows
   which zone grew a decoration. It asks the walkability guard's rule before each seal.

Flow: the growing order builds the ground rules once per level. For each zone in order, the
zone dresser draws a decoration and asks the ground rules about each blocking cell, its own
zone's or a neighbour's. It then asks the walkability guard to place it. After the last zone,
the zone ledger subtracts the level's blocked tiles from each zone. The border closing runs
next and keeps every open neighbour of a sealed tile on the network, whatever its zone. The
final island check runs last, unchanged.

### Level 2

Ground rules:

| Concept | Owns | Never knows |
|---|---|---|
| Reserved tiles | the union over the level of webs, entrance bands, town rooms and bodies, landings, doors and taken tiles | which zone reserved a tile |
| Crossable land | the neighbour land tiles a zone's decoration may block: land of another zone, not reserved, not yet blocked | the zone dresser's draw |
| Terrain fit | whether an identity may stand on the terrain under a cell | zones |

Walkability guard:

| Concept | Owns | Never knows |
|---|---|---|
| Window | the part of the level one zone's placements can touch: the zone's box grown by the largest decoration reach, plus an outer ring no decoration may block | the rest of the level |
| Blocked state | how many decorations block each tile of the window, seeded with what earlier zones grew | who placed them |
| Way out | the network tiles inside the window, of any zone's path web | what lies past the window |

Zone dresser:

| Concept | Owns | Never knows |
|---|---|---|
| Target | the zone's own tiles to cover | neighbour tiles |
| Candidate | one identity at one position whose blocking cells cover a target tile | legality |
| Score | target tiles covered minus own off-target tiles covered, with crossing cells counting as neither | walkability |

Growing order, zone ledger and border closing are each one concept here. Their names are the
parts. The border closing's own concepts stay as they are, except its walkability rule.

## 3. Invariants

1. No blocking cell stands on a reserved tile. Owner: reserved tiles. The ground rules refuse
   the cell.
2. Every blocking cell stands on terrain its identity allows. Owner: terrain fit.
3. Every open land tile reaches the walkable network. Owner: the final island check, which sees
   the whole level. The walkability guard upholds it for every placement. The border closing
   upholds it for every seal, on both sides of a zone border.
4. A zone's open and walkable tiles exclude every blocked tile, whichever zone grew it. Owner:
   zone ledger.
5. The same seed gives the same map. Owner: growing order.

## 4. Forces and patterns

Forces:

- F1. Generation at 144 has little time margin. The walkability check runs once per placement,
  so its area must stay near one zone's.
- F2. Two samplers, field and Gibbs, share one canvas. A legality change must reach both
  without touching either.
- F3. Each terrain has its own mix and its own coverage target. A zone draws from its own mix
  only.
- F4. Zones grow one after another. A later zone must see what earlier zones grew. An earlier
  zone cannot see what later zones will grow.

Patterns:

- Between parts: one value handed along. The growing order hands each zone a level brief with
  the reserved tiles and the blocked state so far, then folds the zone's growth back in. (F4)
- Window bounded by an open ring for the walkability guard. The check stays within the zone's
  box plus the decoration reach. (F1) The ring is never blocked and is not a way out. A tile
  outside the window reaches the network either around the window or through the ring, and the
  ring stays joined to a way out inside the window. So a placement the guard accepts walls off
  nothing anywhere on the level. The price is a refused placement whose only way out leaves
  the window (A1).
- Legality lives in the canvas, the one object both samplers place through. (F2)
- Plain functions for the ledger and the reserved tiles. They have no variation.

Claims:

1. Kept. F3 forces one mix per zone.
2. Rejected. No force behind it, and the corpus contradicts it.
3. Reshaped into the window bounded by an open ring. F1 bounds its size, and F4 needs
   neighbour tiles in it.
4. Rejected. The ground rules check the cells, so the anchor tile carries no rule of its own.
   The anchor only has to lie in the window.
5. Out of this note. It is the separate fix of trying every position of the drawn decoration.
6. Kept, with crossing cells counting as neither gain nor spill (A2).
7. Reshaped into the zone ledger, invariant 4.
8. Kept as the owner of invariant 3.
9. Rejected. A path tile on a zone border has neighbours in the next zone, and invariant 3
   holds for them too. The border closing checks every open neighbour, whatever its zone.

Open lookups: whether any later step reads a zone's tiles minus its own growth instead of the
published open set (A4), and whether the Gibbs energy reads the zone mask in a way the window
changes.

## 5. Mapping onto the existing system

Revision log:

- Section 2, walkability guard, Exit: revised to Way out. The prototype counted the window's
  outer ring as a way out. 45 of 90 maps then failed with walled-off pockets, because land past
  the ring can be a dead end. A whole-level check fixed all but one and cost 42 s more at 144.
  With only network tiles as ways out, no map formed a pocket during growth.
- Section 2, level 1: added the border closing. On 4 of the 84 rerun maps the border closing
  sealed a path tile on a zone border and cut off a few tiles of the next zone, because it
  checked its own zone's side only. Crossing pieces make that neighbour land thinner.
- Section 3, invariant 3: the border closing upholds it on both sides of a border.
- Section 7, A1: replaced by the measured cost of the open ring.

- Ground rules: reshape. `ZoneCanvas.blocked_cells` refuses any cell outside the zone. It gains
  a crossable mask and keeps its terrain and footprint checks.
- Reserved tiles: new. The grower builds them from each `PlanZone`'s web, town room and town
  body, plus the landings and taken tiles it already reads.
- Walkability guard: reshape. `ZoneCanvas` builds its box from the zone tiles. The box grows by
  the reach plus one. `solid` marks land of any zone as open. `protm` takes the level web
  inside the box. `blkcnt` starts with earlier zones' cells. `connect.py` stays as it is.
- Zone dresser: reshape. `_FieldRun._in_zone` tests the anchor against the zone. It tests
  against the window instead. `_fill_score` counts crossing cells as spill. It counts them as
  neither.
- Growing order: reshape. `grow_level` keeps `blocked` per zone. It keeps one level-wide
  blocked set and passes it in the zone's brief.
- Zone ledger: reshape. `grow_level` builds each `VegetatedZone` right after its own zone grows.
  It builds them after the last zone.
- Border closing: reshape. `border_plan.py` `_Sealer.bridges` checks the open neighbours of a
  path tile in its own zone only. It also requires that closing the tile cuts no open tile off,
  the same test `_Sealer.cut_off` runs for a plain tile. The design is right and the code
  is wrong: the 4 failed maps each traced back to one such seal.
- Final island check: exists, `vegetation/step.py` `_check_islands`.
- The brief: `SampleOptions` gains the crossable tiles and the blocked state so far.

## 6. Slices

1. Prototype in a scratch script that patches the canvas and the grower. Done when the sweep,
   the corpus measures and the 144 timing are in. Done 2026-10-11, 30 seeds at each of 36, 72
   and 108:

   | variant | maps failed | starts missing a sawmill | lone pieces per 100 thin-strip tiles at 36 | big pieces across two zones |
   |---|---|---|---|---|
   | today | 0 of 90 | 1 | 12.7 | 1% |
   | crossing | 0 of 90 | 3 | 10.3 | 3% |
   | crossing and every position | 0 of 90 | 6 | 8.2 | 2% |
   | every position, today's guard | 3 of 90 | 6 | 8.1 | 1% |
   | every position, level guard, no crossing | 0 of 90 | 4 | 9.2 | 1% |
   | corpus | | | 8.4 | 12% |

   Size 144 takes 41 to 49 s of CPU for the whole map in every variant. Crossing misses the
   straddle target, because the sampler rarely proposes a crossing piece. The lone-piece gain
   comes from trying every position. Today's guard walls off neighbour land once pieces pack
   tighter, and the level guard fixes that without crossing. Starting towns miss their
   sawmill more often in every denser variant.
2. The canvas, the grower and the border closing's rule in source, with tests: a decoration
   may block a neighbour's tile, never its web or town room. A neighbour's open set excludes the
   crossing cells. The border closing never seals a path tile that cuts off the next zone's
   land. Done when `make check` passes.
3. Trying every position of the drawn decoration. Done when thin-strip lone pieces reach the
   section 1 target.
4. Sweep, golden update and the AGENTS.md lines for the canvas and the grower.

## 7. Assumptions

1. **Assumption**: few crossing placements need a way out beyond the window. **Decided**: the
   window's ring is not a way out, so those placements are refused. **Basis**: on seeds 103 and 106 at size 36 the
   ring refused no placement the old exits accepted. Crossing tries are few to begin with,
   11 to 23 of about 240 placements per map.
   **If wrong**: the window grows, which costs time at 144 (A3).
2. **Assumption**: a crossing cell should not count against the zone that grows it.
   **Decided**: the score ignores it. **Basis**: corpus big pieces straddle zones 12% of the
   time. **If wrong**: the score.
3. **Assumption**: growing the box by the decoration reach keeps size 144 within its time.
   **Decided**: the reach is the largest blocking offset in the models. **Basis**: none. The
   prototype times it. **If wrong**: the window concept.
4. **Assumption**: later steps read each zone's open tiles only from the published open set.
   **Decided**: the ledger is the only fix downstream. **Basis**: `VegetatedZone` is the
   vegetation step's per-zone output. **If wrong**: each reader that subtracts its own growth.
5. **Assumption**: borders end up denser where an earlier zone met its target and a later
   neighbour adds crossing pieces. **Decided**: accept it. **Basis**: corpus rims are denser
   than middles, 48% against 39%. **If wrong**: the crossing cells count toward the neighbour's
   target.
