# core/planning/

What each zone is planned to be before any tree grows: its entrances, its walkable web, the
sea plan and the player zones, and the one record each zone carries through the placement
steps.

## Map

- `borders.py`: `zone_owner`, `cross_pairs` and `closing_pairs`, the zone border geometry that the vegetation
  border plan reads. `closing_pairs` leaves out the crossings of an open pair.
- `entrances.py`: each zone's fronts, its `Gate` values and the planned entrances. `Passages`
  holds each zone's entrances and the open pairs. `plan_passages` gives a gated pair one or two
  entrances, an open pair its whole front and a closed pair none. `all_passages` plans every
  pair as gated. Every function reads the zone label grid, never the zones dict.
- `web.py`: `protected_web`, one zone's spanning backbone and rim gate bands, which the zone
  plan and the vegetation sampler keep free of blocking objects.
- `player_zones.py`: `select_player_zones`, the greedy max-min pick of the player zones. The `preferred` zones that can host a town go first, and the greedy pick fills the rest.
- `zone_plan.py`: each zone's entrances, walkable web and sea plan, read from the place map's `Passages` when the terrain model gave them, and the player zones with the room kept for their town. `VegetationStep` builds it first. `plan_player_zones` reads a `HomeRequest`: the player count, the content plan's homes as `preferred` and the map `size`. A preferred zone's town room lets its sprite overlay reach past the zone and onto the entrance bands, while the blocking cells, the entrance and the approach stay inside.
- `content.py`: the content intent of each place (map-math 5.1 and 5.2). `ContentPlan` holds the player homes and, per planned place, its role, its hop count from the nearest home, its reward scale and its guards' mean level. `ContentTable` reads both off the corpus `PlaceContent` rows by role and hop bin, each cell shrunk toward its hop bin and each bin toward the level. `HopContent`, the one `ContentPlanner`, reads the place map. Every consumer reads `ContentPlan()` as "keep your own default".
- `guarding.py`: the guard in front of each prize in a cut-off place (effort-reward §2). `GuardReading` pools the corpus guard levels by hop bin, falling back to the whole level and then to every monster level. `prize_guard` builds one level's `PrizeGuard`, which draws a level from the spread at the place's hop. The gated tent and monolith partners, the portal guard and the deep pocket guard all draw from it.
- `pricing.py`: what a cut-off place costs and holds (effort-reward §3). `effort_with` builds the effort map from every home with extra objects on it, `price_at` prices a place at its cheapest reached tile into a `Price` with its band, and `CutoffPlace` holds a place's opener, price and prizes. `PrizeCount` reads a place's prize count off its area from the corpus place statistics. A place no home reaches raises `UnreachedPlaceError`.
- `zone_index.py`: `ZoneRecord`, one zone's tiles and reach, the per-level claimed cells, and the per-level zone records and walk targets the placement steps after vegetation share. Every `ZoneRecord` is built here.
