# core/steps/roads/

## Map

- `layer.py`: the `RoadLayer` role, the `RoadLevel` it receives and `NoRoads`, the markov terrain's layer, which lays nothing.
- `network.py`: `PassageRoads`, the places terrain's layer, and `lay_network`, which grows a road from each player town through the planned passages to the sites of the places it reaches. `rules_of` turns the corpus `RoadStats` into the step penalty, the road budget, and the crossing rate per pair. Every road tile takes the level's one surface.
- `route.py`: `route`, the least-cost path over tile and heading with a turn cost.
- `sites.py`: `road_level`, one level read for roads: walkable tiles, places, border kinds, passages, each player town's approach tile and each place's important visit tiles. `map_surface` draws the map's one road surface from the corpus surface counts of every level.
- `step.py`: `RoadsStep`, which draws the map's one road surface, builds each level's `RoadLevel` and writes the layer's roads into `map_state.roads`. It places no object.
