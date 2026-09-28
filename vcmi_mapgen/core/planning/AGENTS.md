# core/planning/

What each zone is planned to be before any tree grows: its entrances, its walkable web, the
sea plan and the player zones, and the one record each zone carries through the placement
steps.

## Map

- `entrances.py`: each zone's fronts, gate bands and planned entrances.
- `zone_plan.py`: each zone's entrances, walkable web and sea plan, and the player zones with the room kept for their town. `VegetationStep` builds it first.
- `zone_index.py`: `ZoneRecord`, one zone's tiles, reach and used cells, and the per-level zone records and walk targets the placement steps after vegetation share. Every `ZoneRecord` is built here.
