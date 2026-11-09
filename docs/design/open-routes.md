# Open routes: regions a hero crosses straight

Disclosure: this note was written after reading the vegetation code in the same session. The
field sampler, its canvas, the protected web and the border seal were all read before the
design began. Each design decision taken from them is a claim in 1b, and each part and concept
below was checked against the question "would I have named this without having seen the code?"

## 1. Problem

A player crossing a generated map walks about 30% further than on a real map to reach the
same spot. The land reads as a maze of one-tile lanes that turn at right angles, while real
maps run fairly straight bands of open ground through each region. Density, region outlines
and the wall at region edges already match the corpus.

Done looks like this, read by `readings` on seeds 1 to 10:

- Route winding on finished maps sits inside the corpus spread at every size. The corpus
  median is 1.29 at 36, 1.30 at 72, 1.27 at 108 and 1.31 at 144. Today generated maps read
  1.47, 1.69, 1.71 and 1.85. The gap grows with the map.
- A region crossed on foot takes about 1.34 times its natural width, against 1.70 today.

Out of scope:

- The region graph: how many regions, which borders are closed, gated or open, and where the
  doors stand. Its readings already match the corpus.
- The amount of blocked land and its profile by distance from a region edge. Both match
  (75%, 61%, 50% blocked at edge distance 1, 2, 3 on the corpus, against 77%, 57%, 49%).
- Water and coast shapes.

## 1b. Claims

From the existing vegetation code:

1. The blocked mask comes first and open ground is what the planting leaves behind.
2. A cellular field shapes the blocked mask: walls on cell edges, one room per cell.
3. A protected web, a spanning tree of 4-connected shortest paths, is the only open ground
   the planting must keep.
4. A placement is legal when every open 4-neighbour still reaches the web.
5. An obstacle may block as many tiles off the plan as on it.
6. Every zone edge outside its entrance bands is planted solid before the interior.

## 2. Parts and concepts

### Level 1: parts

1. **Route drawing.** It decides which ground of a region stays open, as bands that join the
   region's ways in and out and its sites. It owns the shape of the open ground. It never
   knows which obstacles will stand on the rest. It hands the open ground to obstacle
   planting.
2. **Obstacle planting.** It covers the ground the routes leave with real obstacles of the
   region's terrain at the corpus density. It owns which obstacle stands where. It never
   changes the open ground it was handed.
3. **Site placement.** It stands towns, mines, treasure and guards. It owns where each site
   stands. It never blocks a route's through lane. It hands nothing back to route drawing.
4. **Judging.** It reads the finished map beside the corpus. It owns the readings. It never
   knows how the map was made.

Flow: route drawing runs once per region before any obstacle. Planting runs next on the rest.
Site placement runs after planting, and stands beside routes, not across them. Judging reads
the finished map.

### Level 2: concepts

Route drawing:

| Concept | Owns | Never knows |
|---|---|---|
| Waypoint | One spot a route must reach: a way in, a way out, a site's front. | How routes join. |
| Route | The open band between two waypoints, near straight, its bends from smooth noise. | Obstacles. |
| Route net | The set of routes that joins every waypoint, with the loops the corpus shows. | Band width. |
| Band width | How wide a route runs, drawn from the corpus lane and room shares. | The route's path. |
| Open pocket | Open ground off a route, sized from the corpus rooms. | Routes. |

Obstacle planting:

| Concept | Owns | Never knows |
|---|---|---|
| Planting plan | The tiles to block: the region minus its open ground. | How the open ground was drawn. |
| Planter | Which obstacle identity covers which planned tiles, inside the plan only. | Routes. |

Site placement: one concept, **route lane**, the through tiles of each route that a site may
not stand on. It is a shared value type that route drawing produces and site placement reads.

Judging: **route winding**, the median walk over the straight line. It exists.

### Level 3

None. Every concept holds one responsibility.

## 3. Invariants

1. The open ground of a region is connected and reaches every waypoint. Owner: route net.
2. No obstacle blocks a tile of the open ground. Owner: planter. It refuses the placement.
3. No site stands on a route lane. Owner: site placement. The placement step that stands a
   site refuses a spot on a lane.
4. Each map's route winding sits inside the corpus spread at its size. Owner: judging, through
   the sweep.

## 4. Forces and patterns

Forces:

- F1. The way open ground is shaped varies, and the old way must stay switchable for
  comparison. The `--vegetation` switch already chooses between samplers.
- F2. Route shape and band width vary apart. Tuning one must not move the other.
- F3. Planting rules (terrain, footprint, ground) must stay shared between every sampler.
- F4. Speed: the 144 map stays within its time budget.

Patterns:

- Between parts: one value handed along, the open ground of each region, from route drawing
  to planting and on to site placement as the route lane (F2, F3).
- Route drawing is a new sampler variant behind the existing sampler role (F1). The cellular
  field stays as a variant. The choice stays at the CLI.
- Band width and pocket size are plain functions of corpus numbers (F2). No pattern.
- Planter: the existing planting, with the open ground as forbidden ground (F3).

Claims:

1. Rejected. Open ground comes first. Planting leftovers is what makes the maze.
2. Rejected for the new variant. Kept as the old variant (F1).
3. Rejected. The route net replaces the spanning tree. It adds loops and draws near-straight
   8-connected bands.
4. Kept as a guard, now trivially true: the open ground is connected by construction.
5. Rejected. Spill off the plan eroded 13% of the planned open ground on seeds 1 to 4.
6. Kept. The edge profile already matches the corpus.

Lookups (resolved in section 5): where sites choose their spot, and whether the route lane
can reach them without a new port.

## 5. Mapping onto the existing system

Revision log:

- 2026-11-08, section 7 assumption 3 and slice 1: real maps lose only 0.02 of winding to their
  sites (1.30 with vegetation alone, 1.30 finished, 71 maps at 72). Slice 1's target is now the
  corpus vegetation-only median, 1.30, not 1.25.
- 2026-11-08, planting plan: a bin's blocked share moves off the routes onto the bin's other
  tiles, and the routes planter tops up its plan until it blocks the plan's count. Without
  both, finished maps left 0.41 of the land walkable.

- Route drawing: **New**. A `routes` sampler under `core/steps/vegetation/routes/`, beside
  `field/` and `gibbs/`, behind the `Sampler` protocol
  (`core/steps/vegetation/sampler.py:34`).
- Waypoint: **Reshape**. The protected web already gathers entrance bands, the town front
  and extra nodes (`core/planning/web.py:126-133`). The farthest-point nodes join them only to
  cover the zone. The design drops those cover nodes. Pockets cover the zone instead.
- Route: **New**. Today's paths are 4-connected shortest paths (`core/grid/paths.py:14`).
- Route net: **Reshape**. `_span` joins each node to the nearest joined node, a tree with no
  loops (`core/planning/web.py:52-76`).
- Planting plan and planter: **Exists, reshape**. The field run fills a target mask
  (`core/steps/vegetation/field/sampler.py:60-80`). Its score accepts as much spill as gain
  (`field/sampler.py:133`). The routes variant passes its open ground as `forbid`, so spill
  onto it is illegal (`canvas.py`, `blocked_cells`).
- Route lane: **New** as a published value on `VegetationResult`. Gameplay spot choice reads
  it through the context like every other result.
- Route winding: **Exists** (`core/reading/winding.py`).

The existing system has the border seal and the zone edge ring. Both stay (claim 6).

## 5b. What must not move

| Receiver | Gets today | Enforced by | Before | Holds when |
|---|---|---|---|---|
| Player reading density | Walkable share of land | nothing | 0.367 (seeds 1 to 4, 72) | 0.33 to 0.40 |
| Player reading regions | Region count | nothing | 18 (seeds 1 to 4, 72) | 15 to 21 |
| Edge walls | Blocked share at edge distance 1 | nothing | 0.77 | 0.72 to 0.80 |
| Corpus-matched readings | Lane share, open ground share, room count | `readings` | 0.43, 0.19, 11.5 | inside corpus q1 to q3 or closer |
| Map connectivity | Every site reachable on foot | island check, portal check | passes | passes |
| Golden maps | Hashes in `data/pp/golden.json` | `make golden` | pass | regenerated on purpose |
| 144 speed | 57 to 60 s CPU | nothing | 57 to 60 s | under 66 s |

Section 3 adds the density, region-count and edge rows as checks in the sweep. They are not
owned by a unit.

## 6. Slices

1. **Routes sampler on vegetation alone.** Waypoints, near-straight routes with corpus band
   width, loops, pockets, planting around them with no spill. Behind `--vegetation routes`.
   Done when route winding after vegetation reads at or below 1.25 on seeds 1 to 4 at 72
   (today 1.52), and every 5b row holds.
2. **Sites keep route lanes.** Publish the lane and refuse site spots on it. Done when finished
   maps read route winding inside the corpus q1 to q3 at 72 and 36, and every 5b row holds.
3. **Default and sweep.** Make `routes` the default, run the sweep at 36, 72, 108 and 144,
   regenerate goldens. Done when every size reads inside its corpus spread and 144 stays under
   66 s.

## 7. Assumptions

1. **Assumption**: the maze comes from how open ground is shaped, not from how much of it there
   is. **Decided**: shape routes first and keep density. **Basis**: the edge profile and the
   walk share match the corpus while winding does not. A smoother field at the same density
   moved winding from 1.64 to 1.53. **If wrong**: section 2, route drawing.
2. **Assumption**: corpus regions run about 1.34 times their width on foot, so near-straight
   routes with mild bends match them. **Basis**: walkable diameter over the square root of area
   on 71 corpus maps at 72. **If wrong**: route bend amplitude.
3. **Assumption**: sites placed after vegetation cause about a third of today's gap.
   **Basis**: winding rose from 1.52 after vegetation to 1.64 on finished maps, seeds 1 to 4.
   **If wrong**: slice 2's scope. **Proved partly false**: corpus sites add 0.02. Ours add 0.05
   to 0.13, so slice 2 still has a gap to close, but the corpus sets the bar at 0.02.
4. **Assumption**: band width near 2 tiles matches the corpus lane share of 0.34 to 0.43.
   **Basis**: none measured per band. **If wrong**: band width.
5. **Assumption**: drawing routes costs less than the cellular field. **Basis**: none.
   **If wrong**: 5b speed row, slice 3.

## 8. Slice 1 result (2026-11-08)

Seeds 1 to 8, side 72, `--vegetation routes` against the field.

| Reading | Corpus | Field | Routes | Holds |
|---|---|---|---|---|
| Winding after vegetation | 1.30 | 1.53 | 1.40 | no, target 1.30 |
| Winding, finished map | 1.30 | 1.62 | 1.45 | no |
| Winding, finished map at 36 | 1.29 | 1.44 | 1.40 | no |
| Walkable share, finished | | 0.376 | 0.400 | yes, at the bound |
| Region count | | 17.5 | 17.5 | yes |
| Blocked share at edge distance 1 | | 0.745 | 0.735 | yes |
| Lane share | 0.26 to 0.49 | 0.501 | 0.424 | yes |
| Open share | 0.03 to 0.28 | 0.094 | 0.166 | yes |
| Room count | 4 to 17 | 7 | 14 | yes |
| Golden maps | | pass | default unchanged | yes |
| 144 CPU, seed 1 | | 85 s | 141 s | no |

Two findings fall outside slice 1's parts:

- The border seal holds most of the remaining winding. With the seal off, vegetation alone
  reads 1.26 and the walkable share moves by 0.015. Real maps leave a way through between 67%
  of neighbouring regions, with 0.87 openings per pair. Routes maps leave 57% and 0.69.
- The 144 slowdown is in gameplay siting, not in the sampler, which costs about 6 s. Siting
  tries 64,000 spots on a routes map against 26,000 on a field map before each object finds
  its footing.

## 9. Default and doors (2026-11-09)

`routes` is now the default sampler. Two more changes landed with it.

- Doors between territories are placed by geometry. On each level the doors first join
  every territory, shortest pair first. A touching pair also gets a door when the doors so
  far walk it more than 1.4 times its own length or more than `MAX_HOP` doors apart. Each
  door stands on the zone pair nearest the line between the two territories' centres. The
  old rule drew a random spanning forest and put each door on a random zone pair.
- The routes sampler takes every protected rim tile as a way in, doors on taken ground
  included. Without that, no route headed for a door.

Each change alone did little. Together they matched walks between territories at 72 (1.38
against the corpus 1.38). Walks inside a territory already matched.

Finished maps, ffa, against the field default at the commit before:

| Side | Corpus | Before | Now | Maps, no crash |
|---|---|---|---|---|
| 36 | 1.29 | 1.44 | 1.31 | 16 of 16 |
| 72 | 1.30 | 1.65 | 1.37 to 1.50 | 20 of 20 |
| 108 | 1.27 | 1.71 | 1.47 | 6 of 6 |
| 144 | 1.31 | 2.07 | 1.83 | 3 of 3 |

Doors per territory at 72 read 1.7, inside the corpus 1.3 to 2.0. A 144 map takes 125 s of
CPU against 105 s for the field on the same machine.

### Open: gameplay squeezes the open ground

After vegetation, the walkable tiles outside every open 2x2 square make up 0.268 of the
walkable land at 72, against 0.261 for the corpus with its gameplay objects removed. The
gameplay step lifts that to 0.52. The corpus rises only to 0.34. Every kind of object narrows
two to three times more than the same count does on a corpus map: the corpus sets objects
against the tree clumps, and ours split open patches. At 144 the squeeze is worse and the
vegetation share rises to 0.60 against 0.575. A hard rule against narrowing brought the lane
share to 0.40 but cost a quarter of the dwellings and tripled the gameplay time. A soft
preference kept every object and moved nothing. The fix belongs to gameplay siting.

## 10. Walls at 144 (2026-11-09)

At 144 the extra walking sat between territories and showed before any object stood. The
planned walls between territories two or more doors apart took 27% of the zone land at 144
against 6% at 72. Each width grew with the map side, `side // 24` and `side // 18`, so 6 and
8 tiles at 144. The corpus distance between such pairs barely grows with the side: the first
quartile reads 5 and 6 tiles at 72, and 6 and 7 at 144. Each width is now fixed at its value
at side 72: 1, 3 and 4 tiles.

Tried and dropped on the way:

- Alcoves, notches left in the tree edge for gameplay bodies, with a placement pass that
  fills a notch first. Objects used few of them, because siting picks the area by hero-days
  and spacing before the footing picks the tile. The one-tile lane share fell from 0.53 to
  0.47 at 144, the walk barely moved, and a 144 map took twice as long. The patch is kept
  outside the repo.
- Capping the route distance in the planting field. Tree clumping stayed at 0.71 at 72.
- Planting one row of each region border instead of two. It matched the corpus clumping at
  72 (0.55 against 0.56) but walked worse at 72 and left 144 unchanged.

Walk over the straight line, 2 players, seeds 1 to 6 at 144, before and after:

| Seed | 1 | 2 | 3 | 4 | 5 | 6 | Median |
|---|---|---|---|---|---|---|---|
| Before | 1.58 | 1.45 | 1.60 | 1.46 | 1.61 | 1.55 | 1.57 |
| After | 1.57 | 1.25 | 1.39 | 1.29 | 1.38 | 1.31 | 1.35 |

The corpus reads 1.22, quartiles 1.19 to 1.30. The tree share falls from 0.56 to 0.64 down to
0.53 to 0.59, against 0.575 on the corpus. With 4 players, seeds 1 to 4, the walk reads 1.27
at 36, 1.35 at 72, 1.39 at 108 and 1.42 at 144. Sides 36 and 72 keep their walls, so their
maps and the golden hashes do not change. Two 6-player maps at 144 with an underground take
106 and 122 s of CPU. The `readings` spread at 144 keeps `close_pair_walled` inside the
corpus spread (0.24 against 0.03 [0, 0.5]).

Open: seed 1 at 144 still reads 1.57.
