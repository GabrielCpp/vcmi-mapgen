# Territory Topology

A player on a generated map often sees the next territory across three tiles of trees and
cannot get there. On seeds 3, 9 and 10 at size 72, one close pair in four to one in two
needs three fights or more, or has no way at all. The hero walks two hero-days around a
wall to reach land two tiles away. A player on a corpus map pays one fight for that
crossing and walks one day. Seed 5 at size 72 does not generate at all: the treasure step
finds a loot zone no home reaches over the doors.

The cause is the graph-first front. The generator draws a place graph before any shape
exists, lays it out by MDS, and then keeps only the planned pairs open. Every pair the
growth realised but the graph never planned becomes a wall. The corpus has no such notion.
Its territories touch on the ground, and the ground decides where the doors go.

This plan replaces that front with shapes first. The map grows its places, counts its
territories from a corpus prior, draws doors on the realised fronts, and only then paints.
`docs/design/map-math.md` §2.1 holds the model. This document holds the evidence, the
settled decisions, and the slices in order. Each slice ends with `make check` green and a
fresh set of golden hashes.

The scratch scripts that measured everything live in the session scratchpad as `topo.py`
and `fix.py`. The implementer re-creates `topo.py` as a reading once slice 1 needs it.

---

## 1. Evidence

Every row below reads territories with `read_territories` on level 0, then takes every
territory pair whose closest tiles lie within 3 tiles of each other. These are the pairs a
player sees as neighbours. Values are medians over maps. Door hops counts the doors a hero
crosses on the shortest door path between the two territories.

| Front | Maps | Territories | Loops | Doors | Close pairs | Door hops | 3+ hops or cut | Walled close pairs | Toll-free days |
|---|---|---|---|---|---|---|---|---|---|
| Corpus, side 72 | 70 | 11 | 1 | 9.5 | 9.5 | 1.04 | 0.06 | 0.16 | |
| Corpus, all sides | 155 | 11 | 1 | | | 1.00 | 0.08 | 0.16 | |
| Ours, 72, seeds 1 to 10 | 9 | 15 | 1 | 15 | 18 | 1.40 | 0.05 | 0.38 | 2.0 |
| Ours, door rule | 10 | 12 | 5 | 16 | | 1.15 | 0.00 | 0.15 | 1.0 |
| Ours, count rule | 10 | 9 | 1 | 8.5 | | 1.50 | 0.08 | 0.36 | |
| Ours, both rules | 10 | 8.5 | 2 | 9 | 9 | 1.19 | 0.00 | 0.16 | 1.25 |

Seed 5 crashed in the base run and generated under every fix. Seeds 3, 7, 9 and 10 carry
the detours: 0.23, 0.14, 0.28 and 0.55 of their close pairs need three hops or more. The
median hides them.

Door share by distance between the two territories' closest tiles:

| Distance | Corpus doors | Ours doors |
|---|---|---|
| 2 | 82% | 64% |
| 3 | 75% | 58% |
| 4 | 50% | 33% |
| 5 | 14% | 20% |
| 6 | 16% | 9% |

The corpus walls at distance 3 are land walls in 66 cases of 79. Water carries the walls at
distance 4 to 6 in one case of three.

The underground is the control. Ours at level 1 with `--subterrain` reads 5 territories, 0
loops, every close pair at 1 hop, nothing walled. The corpus level 1 reads 7 territories, 0
loops, every close pair at 1 hop, nothing walled. The underground has no plan and draws
its doors on the realised borders. It matches the corpus. The surface has a plan and does
not.

Corpus territory counts on level 0 by side and player count, from
`read_territories`: side 72 with 2 players 2, 4, 8, 9, 9; with 3 players 5 to 16, median 9;
with 4 players 29 maps, median 11; with 5 players median 11; with 6 players median 10.
Side 36 with 2 players 3 to 6. Side 108 with 4 players 11 to 21. Side 144 is sparse.

The seed 5 log at `--stop-after vegetation` prints 26 places planned and grown, 8 planned
borders missing, 21 territories, 17 doors and 23 walled borders. The treasure step then
raises `UnreachedPlaceError` for loot zone 19. The reachability check in slice 1 will name
the missing door. The door rule removed the crash in every run.

## 2. Settled decisions

- The words stay territory and place.
- The front is top-down. The generator counts territories first, grows them, and splits
  them into places. A new prior gives the territory count per map by players and land.
- Doors go on the ground. A spanning forest links the territories, then every touching
  pair whose door-hop distance exceeds 2 gets a door, with no loop budget. A second door on
  one pair follows at the corpus odds. Open question 1 records why the hop rule wins.
- Water comes after the territories. In topology mode it is the thick wall kind on
  doorless pairs, with a width. Islands mode keeps its noise mask.
- Both levels share one front. The underground is the case with no home. Subterranean
  gates count as doors.
- The place graph draw and the graph-driven layout go last, after the front stands on its
  own. `grow_regions`, `group_neutral`, `settle`, `draw_doors`, `walled` and
  `PlannedDoor` stay.
- No fixed tile buffers. Every width and gap derives from the map side.
- Golden hashes change on every slice. The implementer runs `make golden-update` at the
  end of each slice and commits the new `data/golden.json` with it.

## 3. Slices

### Slice 1: door rule and territory count inside `bordered`

Goal: a player reaches every territory three tiles away in one fight, on seeds 1 to 10 at
size 72, and seed 5 generates. The territory count lands on the corpus curve for the map's
side and player count.

Roles and interfaces:

- `core/priors/territories.py`: `TerritoryStats` gains
  `counts_by_map: tuple[TerritoryCount, ...]`. `TerritoryCount(players: int, land: int,
  territories: int)` is a frozen dataclass beside it. `land` is the count of
  walkable land tiles on the level.
- `corpus/mine/territories.py` `mine_territories` records one `TerritoryCount` per map
  from `read_territories`: territories is `len(read.territories)`. The players value comes from `map_players(...).players`, as `mine_stats.py`
  already passes owners.
- `corpus/territories.py`: `TERRITORY_VERSION` becomes 4, the file gains
  `counts_by_map`, and the loader reads the three fields of each record.
  `mine-stats --only territories` rewrites `data/pp/territory_stats.json`.
- `core/steps/terrain_gen/territories.py`:
  - `draw_territory_count(counts: Sequence[TerritoryCount], players: int, land: int,
    rng) -> int` returns a territory count drawn from one record. It keeps the records
    whose land lies within `LAND_BAND` of the map's, takes the nearest player count with
    `NEAREST_RECORDS` maps, and draws among the `NEAREST_RECORDS` nearest by land as
    `place_graph.place_count` does. With no record it returns the home count plus one.
  - `group_neutral(places, edges, spread, rng)` keeps its signature. `bordered` passes a
    one-value spread computed as `ceil(free places / max(1, m - homes))`, so the neutral
    groups land on `m - homes` territories. The pooled `neutral_zones` prior stays in
    the file for the readings and goes out of the draw.
  - `detour_doors(choices: Mapping[Pair, Sequence[Pair]], joined: Iterable[Pair],
    max_hop: int, rng) -> dict[Pair, int]` walks the touching territory pairs in sorted
    order. For each pair whose door-hop distance over the doors so far exceeds `max_hop`,
    or that no door path joins, it adds one door on a zone pair drawn from that pair's
    choices. `draw_doors` builds the choices: the planned zone pairs of the front when it
    has some, else all of them. No loop budget stops it.
  - `draw_doors` calls `detour_doors` after the forest and before the second-door draw.
    Its signature keeps `pair_doors`. `MAX_HOP = 2` sits beside `MAX_DOORS`.
  - `unreached(plan: TerritoryPlan, realised: Iterable[Pair]) -> list[int]`
    returns the territories no home reaches over the doors within one land component.
    `bordered` logs them beside the stranded and islanded lines.
- `core/steps/terrain_gen/places.py`:
  - `bordered` takes `players: int` and the land tile count. It calls
    `draw_territory_count` before `draw_partition`, passes the computed neutral spread to
    `group_neutral` through `draw_partition`, and calls `draw_doors`.
  - `underground_places` calls the same `draw_territory_count` with `players=0` and the
    level's land count, and the same `draw_doors`.
- `core/reading/vector.py` `territory_vector` gains `territory_count`, `territory_loops`,
  `close_pair_hops`, `close_pair_far` and `close_pair_walled`. `core/reading/territories.py`
  gains `close_pairs(labels, within: int) -> dict[Pair, int]` from `topo.py`, with
  `within` as `max(2, side // 24)` so the rule scales with the map. The `readings`
  command then shows the columns beside the corpus spread.

Corpus priors: `counts_by_map` as above. No other prior changes.

Tests:

- `territories_test.py`: `detour_doors` leaves every touching pair within `MAX_HOP`; it
  joins every far pair and every cut-off pair, however many loops they close; it prefers
  a planned zone pair; the same seed gives the same doors.
  `draw_territory_count` draws among the nearest records by players then land, and falls
  back without records.
- `places_test.py`: `bordered` on a fixed grid gives `m` territories when the records
  allow, and `unreached` is empty.
- `corpus/mine/territories_test.py`: one synthetic map yields one `TerritoryCount`
  with the right territory count, and the saved table loads back the same.
- `cli/generate_test.py`, marked `slow`: `generate --seed 5 --size 72` completes. The
  sweep also runs it through `make sweep`.
- `golden_test.py`: hashes refreshed.

Readings that must move, on seeds 1 to 10 at size 72, level 0: territory count from 15 to
the corpus 11, within 8 to 13; close-pair hops from 1.40 to 1.0 to 1.1; 3+ hops share from
0.05, with seeds 3, 9 and 10 at 0.23 to 0.55, to 0; walled close pairs from 0.38 to 0.16.
Loops rise from 1 to 3 without the budget. Slice 2 should bring them back toward the
corpus, as open question 1 says. Slice 2 brought them to 2.

Measured after slice 1, seeds 1 to 10 at size 72, level 0 medians. Seed 5 fails only in
the measuring harness, which runs the bare catalog. The CLI generates it.

| Rule | Territories | Loops | Close-pair hops | 3+ hops share | Walled close pairs | Seeds |
|---|---|---|---|---|---|---|
| Before slice 1 | 15 | 1 | 1.40 | 0.05 | 0.38 | 9 |
| Loop budget at the corpus map's loops | 9 | 1 | 1.39 | 0.05 | 0.29 | 10 |
| Loop budget one above the corpus map's | 9 | 1 | 1.43 | 0.12 | 0.29 | 9 |
| No loop budget, kept | 9 | 3 | 1.15 | 0.00 | 0.15 | 9 |
| Corpus | 11 | 1 | 1.04 | 0.06 | 0.16 | 159 maps |

The mine promise under each rule: seeds that keep it, seeds with a basic mine more than 3
days further for one player, and seeds with a gold mine within 14 days of a home.

| Rule | 48, 20 seeds | 72, 10 seeds |
|---|---|---|
| Before slice 1 | 4 / 5 / 16 | 1 / 2 / 7 |
| Loop budget at the corpus map's loops | 2 / 8 / 18 | 4 / 3 / 4 |
| Loop budget one above the corpus map's | 2 / 6 / 17 | 1 / 1 / 8 |
| No loop budget, kept | 3 / 4 / 17 | 1 / 4 / 7 |

Golden hashes: both maps change.

Deleted: nothing. The `neutral_zones` draw in `draw_partition` stops being read by the
surface and the underground. The field stays until slice 4.

### Slice 2: barrier thickness by door hops, water on the walled fronts

Goal: a player reads the map at a glance. A thin treeline means one fight away. A wide
band or water means a long way round. Today every walled pair looks the same, and the
topology water stands wherever the graph layout put a mass, not where the walls are.

Roles and interfaces:

- `core/steps/terrain_gen/territories.py`: `wall_depths(territory, realised, doors,
  side: int) -> dict[Pair, int]` gives each walled zone pair a wall width in tiles from
  the door-hop distance of its territory pair: hop 1 thin, hop 2 wide, hop 3 or more
  the band. The three widths derive from `side`: `max(1, side // 72)`, `max(2, side //
  36)` and `max(3, side // 24)`. The implementer confirms the ratios against the corpus
  wall widths before fixing them. `wall_kinds` reads the depth to choose between `CLOSED`
  and a new `AdjacencyKind.BAND`.
- `core/steps/terrain_gen/water.py`: `TopologyForm` stops drawing water before the
  places. It becomes `water_on_walls(grid, plan, depths, target, priors, rng)`, called
  from `surface` after `bordered`. It carves water along the walled fronts whose depth is
  the band, widest first, until the water share reaches the drawn target, then adds the
  corpus edge water. The `masses` field of `WaterTarget` becomes the count of fronts
  carved. `coast` runs after it. Islands mode keeps `NoiseForm` and its mask before the
  places, as today.
- `core/steps/vegetation/step.py` `seal_borders` reads the depth and fills a band wall to
  its width instead of one tree line.
- `result.py` `LevelPlaces` gains `depths: Mapping[Pair, int]`.

Corpus priors: the wall width by door hops. `corpus/mine/territories.py` measures, per
walled close pair, the closest-tile distance and whether water carries it, grouped by door
hops. The prior stores the median distance per hop bin. This is the curve in §1.

Tests: `wall_depths` gives three widths rising with hops and scaling with side; the water
form fills the band fronts first; a surface map in topology mode keeps every door tile on
land; islands mode output is unchanged in hash on the islands golden if one exists, else
on a new islands golden added here.

Readings that must move: the share of walled close pairs carried by water at distance 4
to 6 toward one in three; the door share by distance toward the corpus curve, 82%, 75%,
50% at 2, 3 and 4 tiles.

Golden hashes: both maps change.

Deleted: `water.masses_of` and `_pins` on the graph, `static_features` use of the layout
anchors. `Coastline.layout` stays until slice 4.

Built in slice 2. The land walls landed. The water on the walls did not.

- `territories.py` `wall_depths(territory, doors, side)` gives every zone pair of two
  territories a width from the door hops between them. `WALL_WIDTHS` holds each width as
  a least value and a side divisor: `max(1, side // 72)` one door apart, `max(3, side //
  24)` two apart, `max(4, side // 18)` three or more apart or cut off. That reads 1, 3
  and 4 at side 72, and 2, 6 and 8 at side 144. It covers zone pairs that do not touch,
  so two territories that sit close across a third zone get their wall too.
- `planning/borders.py` `deep_pairs` finds the open tile pairs of two zones closer than
  their width. `border_plan.seal_borders` closes them with the crossings it closed
  before. The nearest open tiles of a walled pair then stand one tile beyond the width.
  The greedy pick now runs on an incremental count heap, so the extra pairs stay cheap.
- `LevelPlaces.depths` carries the widths from `walled` to the vegetation step, on both
  levels.
- `reading/territories.py` reads each territory pair within 5 tiles with its distance
  and whether a door or link joins it. `territory_vector` emits `door_share_d2` to
  `door_share_d5`.

Deviations from the sketch:

- No `AdjacencyKind.BAND`. `AdjacencyKind` is the vocabulary of the corpus reading, and
  the widths ride on `depths`. The kinds stay `CLOSED`.
- No `water_on_walls`. The topology water still lands before the places, where the layout
  put its masses. Moving it needs the layout and paint reorder of slice 4. The islands
  mode is unchanged.
- No wall-width prior. The corpus distance does not grow with the side the way a median
  would need, and the reading window truncates it. The widths are fixed against the
  corpus quartiles below instead.
- Widths 1, 3 and 4 at side 72, not the sketch's 1, 2 and 3. A width of 2 leaves a hop-2
  pair 3 tiles apart, inside the close window of 3 tiles, and the reading would count it
  as a walled close pair.

The corpus closest-tile distance between territory pairs, by the door hops between them:

| Side | Hop 1 median | Hop 2 median (q25) | Hop 3+ median (q25) | Cut off median (q25) |
|---|---|---|---|---|
| 72 | 3 | 8 (5), water in 18% | 10 (6), water in 36% | 7 (5), water in 40% |
| 144 | 3 | 9 (6) | 11 (7) | 9 |

Our walls put a hop-2 pair at 4 tiles or more and a hop-3 pair at 5 or more at side 72,
just under the corpus first quartile. At side 144 they give 7 and 9.

Measured after slice 2, seeds 1 to 10 at size 72, level 0 medians over 9 seeds:

| Rule | Territories | Loops | Doors | Close pairs | Close-pair hops | 3+ hops share | Walled close pairs |
|---|---|---|---|---|---|---|---|
| After slice 1 | 9 | 3 | 9 | 10 | 1.15 | 0.00 | 0.15 |
| Slice 2, no loop budget, kept | 9 | 2 | 8 | 7 | 1.00 | 0.00 | 0.00 |
| Slice 2, loop budget 1 | 9 | 1 | 8 | 7 | 1.00 | 0.00 | 0.00 |
| Slice 2, loop budget 2 | 9 | 1 | 8 | 6 | 1.00 | 0.00 | 0.00 |
| Corpus | 11 | 1 | 9.5 | 9.5 | 1.04 | 0.06 | 0.16 |

The medians hide the outliers. Without a budget, seed 7 reads 1.27 hops with 0.09 of its
close pairs 3 doors apart, and seed 9 reads 1.12. With a budget of 1, seed 9 reads 1.29
and no close pair sits 3 doors apart. With a budget of 2, seed 7 reads 1.33 with 0.11 of
its close pairs 3 doors apart. The budget experiment stops the detour doors that close a
loop once the budget is spent, and always joins a cut-off pair.

Door share by distance between two territories' closest tiles:

| Distance | Corpus | After slice 1 | Slice 2 | Slice 2, loop budget 1 |
|---|---|---|---|---|
| 2 | 82% | 84% (53 of 63) | 98% (43 of 44) | 93% (39 of 42) |
| 3 | 75% | 57% (21 of 37) | 91% (21 of 23) | 88% (15 of 17) |
| 4 | 50% | 10% (1 of 10) | 57% (8 of 14) | 35% (6 of 17) |
| 5 | 14% | 14% (2 of 14) | 4% (1 of 26) | 6% (2 of 31) |
| 6 | 16% | 14% (1 of 7) | 60% (6 of 10) | 12% (1 of 8) |

The walls move the walled pairs out past 3 tiles, so the pairs left at 2 and 3 tiles are
mostly the doored ones. Water carries 19 of the 35 walled pairs at 4 to 6 tiles, against
63% after slice 1 and one in three in the corpus. The topology water still stands where
the layout put it.

The mine promise, as under slice 1:

| Rule | 48, 20 seeds | 72, 10 seeds |
|---|---|---|
| After slice 1 | 3 / 4 / 17 | 1 / 4 / 7 |
| Slice 2 | 6 / 4 / 13 | 1 / 4 / 9 |

Time per map at 144 with 6 players, CPU seconds per step, after slice 1 and slice 2
alternated on the same machine:

| Seed | Terrain | Vegetation | Gameplay | Whole map |
|---|---|---|---|---|
| 1 | 2.2 / 2.2 | 4.8 / 5.5 | 61.4 / 61.3 | 95.7 / 96.8 |
| 2 | 2.8 / 2.9 | 1.7 / 2.2 | 55.3 / 63.5 | 81.3 / 88.5 |
| 3 | 3.8 / 3.9 | 3.3 / 3.8 | 56.9 / 68.6 | 91.9 / 101.2 |

The sealer closes about 1700 cells at 144 against 170 before. Its first `cut_off` flooded
the open land around each pick until the pieces met, and on seed 3 the sealer took 13 s
against 0.4 s. `cut_off` now asks whether two big pieces meet through the walls instead. It
keeps the closed tiles joined 8-way in a union-find that grows with each seal. Two open
4-neighbours of a pick fall apart exactly when a wall on one side of the pick is joined to a
wall on the other side. The sealer costs 1.2 s on seed 1, and the maps come out the same as
with the flood. Terrain costs what it did, and vegetation costs 0.5 to 0.7 s more for the
cells it closes. The gameplay step now carries the extra time: it costs 8 to 12 s more on
seeds 2 and 3. The machine ran other jobs, so the absolute times read high against the 57 to
60 s of 2026-10-10.

Decisions:

- The loop budget stays out. A budget of 1 meets the bar on these seeds and brings the
  loops to the corpus 1, but a budget of 2 puts a close pair of seed 7 three doors apart.
  The result turns on one draw. A fixed budget does not scale with the map, and a budget
  from the corpus map's loops needs a loops field in `TerritoryCount` and a new mine.
  The user decided it after slice 2: the hop cap alone.
- The hop cap stays. It now leaves the door share 16 points above the corpus at 2 and 3
  tiles, past the 10-point bar of open question 2. The excess is on the side of more
  doors, so a player meets fewer detours than the corpus gives, not more. The user
  decided it after slice 2: the cap over the distance curve.

Golden hashes: `s1_48` changes. `s3_72_sub` does not. On that map the sealer closes the
same 49 surface cells with and without the widths.

### Slice 3: one front for both levels

Goal: a player underground meets the same rules as on the surface: territories at the
corpus count, doors on every near front, gates that count as doors.

Roles and interfaces:

- `core/steps/terrain_gen/places.py`: `underground_places` calls `bordered` with
  `players=0` and `owners` all `None`. The special grouping and the all-gated kinds go.
  `bordered` handles the no-home case: no player territories, the whole level grouped by
  `group_neutral`.
- `core/steps/terrain_gen/territories.py` `draw_doors` takes `gates: Collection[Pair]`
  and seeds the door set with them, so a gate pair counts as one hop. `territory_plan`
  emits a `PlannedDoor` for each gate pair with `tiles` set to the gate's site tiles.
- `core/steps/terrain_gen/result.py` `PlaceMap` gains `gates: tuple[PlannedDoor, ...]`
  linking a surface zone to an underground zone.
- `core/reading/territories.py` already reads gates as links. The generated side now
  publishes them the same way, and `inspect territories` prints them as doors.

Corpus priors: `counts_by_map` for level 1 with `players=0`. `mine_territories` already
runs per level.

Tests: `underground_places` on a fixed cave grid gives the drawn count and a connected
door graph; a gate pair reads as one hop in `detour_doors`; `generate --seed 3 --size 72
--subterrain` reads every underground close pair at hop 1.

Readings that must move: level 1 territory count toward the corpus 7, close-pair hops
stays at 1.0, walled stays at 0.

Golden hashes: `s3_72_sub` changes.

Deleted: `UNDERGROUND_ENTRANCE_W` as a separate entrance width if `ENTRANCE_W` scales
with side after slice 2; the underground branch in `underground_places` that marks every
kind `GATED`.

### Slice 4: shapes first, then delete the place graph and the layout

Goal: the map's shapes come from the ground. No retry, no missing planned borders, no
graph-first count. A player sees towns spaced as the corpus spaces them because the
generator chooses homes on the grown shapes.

Roles and interfaces:

- `core/steps/terrain_gen/shapes.py`, new: `grow_shapes(land: Mask, n: int, rng) ->
  Layout` picks `n` anchors farthest-first on the land and grows them with the existing
  `grow` from `layout.py`. `n` comes from `place_graph.place_count` on the land count.
  It never retries.
- `core/steps/terrain_gen/homes.py`, new: `choose_homes(layout: Layout, k: int, rng) ->
  list[int]` picks `k` home places farthest-first among the places `roomy` accepts, and
  accepts the draw when the home gap meets the corpus home separation. On failure it
  takes the best of a bounded number of draws and logs the gap, as `lay_out` does today.
- `core/steps/terrain_gen/roles.py`, new: `label_roles(layout: Layout, homes:
  Sequence[int], territories: Sequence[int], stats: PlaceStats, rng) -> list[PlaceRole]`
  labels the non-home places by a Metropolis walk over the realised adjacency with the
  role-adjacency energy from `stats.adjacency` and the size cost from `stats.sizes`. A
  pocket may only label a degree-1 place. A pass may only label a place touching two
  territories.
- `core/steps/terrain_gen/coastline.py`: `Coastline` loses `graph`. `SurfaceForm.form`
  returns the land mask and the layout only.
- `places.py` `surface` runs: form, `grow_shapes`, `choose_homes`, `bordered` with the
  homes as owners, `label_roles`, palette, identity, paint, water on walls, paint places.
  `plan.adjacency` becomes the realised adjacency. `plan_of` reads the roles from
  `label_roles`.
- `border_kinds.draw_kinds` drops the rule that closes every unplanned pair. Its
  `planned` parameter goes.
- `cli/generate.py` `topology_record` drops `early_graph` and writes `adjacency`, the
  realised pairs.
- `identity.py` and `place_map._renumber` read `plan.adjacency` unchanged, since it now
  holds the realised pairs.

Corpus priors: `stats.adjacency` and `stats.sizes` already exist. The home separation
prior is `target_gap(stats)` and stays.

Tests: `grow_shapes` covers the land and gives `n` places on an open mask; `choose_homes`
keeps homes at least the corpus gap apart on a fixed mask and never picks a cramped
place; `label_roles` puts a pocket only on a degree-1 place and a pass only between two
territories; `surface` on seed 1 logs no missing borders. `place_graph_test.py` and
`layout_test.py` lose the tests of the deleted functions.

Readings that must move: the role-adjacency and size readings in `readings` stay within
the corpus spread; home gap stays at or above today's; the layout line stops printing
missing borders.

Golden hashes: both maps change.

Deleted: `place_graph.draw_graph`, `walk_edges` and the edge draw; `layout.lay_out`,
`classical_scaling`, `graph_distances`, `nudge`, `TRIES` and the retry; `Coastline.graph`;
`water.TopologyForm` graph use; `early_graph` in `topology.json`; `draw_kinds`' unplanned
rule; `TerritoryStats.neutral_zones` and `player_zones` if no reading still reads them.
Kept: `grow`, `grow_regions`, `roomy`, `home_gap`, `snap`, `spread`, `separate`,
`group_neutral`, `settle`, `draw_doors`, `walled`, `PlannedDoor`.

Docs updated in the same change: the stale statements in §5.

## 4. Open questions

Each carries my recommendation. The implementer takes the recommendation unless the user
says otherwise.

1. Door objective. Decided after slice 1: the hop cap alone, with no loop budget. The
   player's complaint is detours, so the hop rule wins over the loop count. Slice 1
   measured both. A budget at the corpus map's loops kept loops at 1 and close-pair hops at
   1.39. A budget one above it kept hops at 1.43. The hop cap alone brought hops to 1.15,
   the 3+ hops share to 0 and walled close pairs to 0.15, at 3 loops against the corpus 1.
   The tables under slice 1 hold the numbers. Slice 2 thickened the walls and brought the
   loops from 3 to 2. A budget of 1 brought them to 1 with no close pair 3 doors apart,
   but a budget of 2 put one of seed 7's close pairs 3 doors apart. The tables under slice
   2 hold the numbers. Decided after slice 2: the hop cap alone, with no loop budget. A
   later budget would come only as a draw from the corpus map's loops, which needs a
   loops field in `TerritoryCount`, and would stay only if the bar holds over 20 seeds.
2. Replacing the hop cap with the distance curve. The corpus door share falls with the
   closest-tile distance: 82%, 75%, 50%, 14%. A rule that draws a door per touching pair
   at the odds of its distance would match the curve without a cap. Slice 2 added the
   curve as a reading. The cap with the slice 2 walls reads 98% and 91% at 2 and 3 tiles,
   16 points above the corpus, past the 10-point bar. Decided after slice 2: the cap
   stays and the curve stays a reading. The excess means more doors and fewer detours
   than the corpus, and the curve would bring back walled close pairs.
3. Barrier thickness. Decided in slice 2: three depths by hop, 1, 3 and 4 tiles at side
   72, each scaled with the side. The water carver does not read them yet.
4. Territory area. Count places per territory only, or also the tile area.
   Recommendation: place count only in slices 1 to 3. The corpus `area` field in the
   scratch records lets a later slice add a tile budget if the readings show territories
   too uneven.
5. Home choice. Farthest-first with the corpus gap as acceptance, or an energy over the
   fairness readings. Recommendation: farthest-first with acceptance. Fairness by
   placement comes after coverage, as the user's rule says.
6. Pockets and islands. Label a pocket on a degree-1 place only, or carve a pocket by
   walling a place off. Recommendation: label only. The islands mode keeps its mask, and a
   water island becomes its own territory through `settle`.
7. Prior pooling for the territory count. Nearest records by players then land, or a
   fitted line on land. Recommendation: nearest records, players first, within the same
   side band. Fall back to the nearest player count with 5 or more maps when the band has
   fewer. A fitted line waits until side 144 has enough maps.
8. Subterranean gates in the surface loop count. A gate joins two levels, so counting it
   in either level's loops double counts. Recommendation: count gates as doors for hops
   and not for loops.

## 5. Stale statements to fix

These lines describe the graph-first front. Slice 4 deletes the code they describe. The
root `AGENTS.md` and `vcmi_mapgen/AGENTS.md` are generated. The implementer edits the
library source and runs `make agent-install`. The file under `core/steps/terrain_gen/` is
hand-written and edited in place.

- Root `AGENTS.md` line 73, source
  `/home/gabriel/Documents/workspace/agent-library/library/skills/projects/vcmi-mapgen/vcmi-mapgen/SKILL.md`
  line 80: "It lays out a place graph and paints each place."
- `vcmi_mapgen/AGENTS.md` line 84, source
  `.../vcmi-mapgen-maps/SKILL.md` line 91: "each zone is one place of the laid-out place
  graph".
- Source `.../vcmi-mapgen-pipeline/SKILL.md` lines 96 to 99: "splits each level into
  territories joined by one-tile doors and walls every other border between two
  territories." After slice 1 the walls hold only where the door hops stay at 2 or
  less.
- `README.md` lines 26 to 30: "A place graph drawn from corpus statistics, laid out on
  land". Line 96: "`topology.json` records ... the early place graph".
- `vcmi_mapgen/core/steps/terrain_gen/AGENTS.md`: the entries for `places.py` ("Its
  `SurfaceForm` gives the place graph and its layout"), `coastline.py`, `water.py`
  ("lays the place graph out on all land"), `place_graph.py`, `layout.py`,
  `border_kinds.py` ("makes every unplanned pair closed"), `territories.py` ("count of
  its early-graph neighbours", "spanning forest ... second door at the corpus odds").
- `vcmi_mapgen/core/steps/terrain_gen/result.py`: the `TerritoryPlan` docstring "Every
  other border between two territories is walled".
- `vcmi_mapgen/cli/generate.py` line 290: the `early_graph` key.
- `docs/plans/territories-and-doors.md` slice 4 "Drawing the partition" and "Border
  kinds" describe the early graph. This plan supersedes those two sections.
- `docs/architecture.md`: no hit.
