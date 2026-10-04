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
- `content.py`: the content intent of each place (map-math 5.1 and 5.2). `ContentPlan` holds the player homes and, per planned place, its role, its hop count from the nearest home, its reward scale and its guards' mean level. `ContentTable` reads both off the corpus `PlaceContent` rows by role and hop bin, each cell shrunk toward its hop bin and each bin toward the level. `draw_level` turns a mean into one random monster level. `cli/steps.py` `CONTENTS` picks the planner: `NoContent` for markov plans nothing, `HopContent` for places reads the place map. Every consumer reads `ContentPlan()` as "keep your own default".
- `zone_index.py`: `ZoneRecord`, one zone's tiles and reach, the per-level claimed cells, and the per-level zone records and walk targets the placement steps after vegetation share. Every `ZoneRecord` is built here.
