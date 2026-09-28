# core/planning/

What each zone is planned to be before any tree grows: its entrances, its walkable web, the
sea plan and the player zones, and the one record each zone carries through the placement
steps.

## Map

- `borders.py`: `zone_owner` and `cross_pairs`, the zone border geometry that the vegetation
  border plan and the border guards both read.
- `entrances.py`: each zone's fronts, its `Gate` values and the planned entrances. Every
  function reads the zone label grid, never the zones dict.
- `player_zones.py`: `select_player_zones`, the greedy max-min pick of the player zones.
- `zone_plan.py`: each zone's entrances, walkable web and sea plan, and the player zones with the room kept for their town. `VegetationStep` builds it first.
- `zone_index.py`: `ZoneRecord`, one zone's tiles and reach, the per-level claimed cells, and the per-level zone records and walk targets the placement steps after vegetation share. Every `ZoneRecord` is built here.
