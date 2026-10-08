# core/steps/roads/

## Map

- `layer.py`: the `RoadLayer` role and the `RoadLevel` it receives.
- `network.py`: `PassageRoads`, the road layer, and `lay_network`, which grows a road from each player town through the planned passages to the sites of the places it reaches. `rules_of` turns the corpus `RoadStats` into the step penalty, the road budget, and the crossing rate per pair. Every road tile takes the level's one surface. `step_cost` adds `COURTESY` to a step onto a shy tile, so a road crosses an object it does not serve only where no other way exists.
- `route.py`: `route`, the least-cost path over tile and heading with a turn cost.
- `sites.py`: `road_level`, one level read for roads: walkable tiles, places, border kinds, passages, each player town's approach tile and each place's important visit tiles. `shy_of` gives the shy tiles: the walkable sprite tiles of every gameplay object, its approach and the tiles a road stops on left out. `map_surface` draws the map's one road surface from the corpus surface counts of every level.
- `step.py`: `RoadsStep`, which draws the map's one road surface, builds each level's `RoadLevel` and writes the layer's roads into `map_state.roads`. It places no object.
