# core/steps/terrain_gen/

## Map

- `model.py`: the `TerrainModel` role `TerrainStep` is given, with `TerrainOptions` in and `TerrainDraw` out. `cli/steps.py` builds the places model, the only one, from a surface form. `SURFACE_FORMS` names the surface forms per water mode, and `DEFAULT_WATER` is `topology`.
- `places.py`: `PlacesTerrain`, the default model: the place-first surface over today's underground. Its `SurfaceForm` gives the place graph and its layout on land, then the palette partition, identity, a base coat and Paint follow.
- `coastline.py`: the `SurfaceForm` role, which returns a `Coastline`: the place graph, its layout with water labelled -1, and its log lines. `NoiseForm` is the variant behind `--water-mode none`, `normal` and `islands`: a noise land mask from `macro.py` first, then the graph and the layout on it.
- `water.py`: `TopologyForm`, the default variant behind `--water-mode topology`. It lays the place graph out on all land, splits the places into land masses with a strait between them, and draws water by Gibbs sweeps over the odds `corpus/mine/water.py` fits. Two multipliers steer the sweeps to one corpus map's water share and edge share. Anchors and gate sites stay land. The underground plans its passages one tile wide and drops tunnel protection on place fronts, so vegetation walls each front except its passage. Its terrain log line reports the drawn and realised palette region counts, the same-terrain share of place borders and the raw cut.
- `paint.py`: Paint, which grades a transition band across each border between places of different dominant terrain, grows accents inside each place, textures each place's interior with the tables counted inside corpus places, and keeps every place's dominant share at the corpus floor through the tiler's erosion.
- `place_graph.py`: the place graph: the corpus place count, roles, sizes and a Metropolis walk over the edges.
- `layout.py`: the place graph laid on land by classical scaling and capacity-bound growth, nudged until the regions border as planned.
- `palette.py`: the palette partition: the corpus palette region count for the place count and land, and `group_places`, which grows that many regions of whole places, each connected on the realised place adjacency, to corpus terrain-blob capacities.
- `identity.py`: one dominant terrain per palette region, drawn by a Metropolis walk over the regions from the corpus terrain of their places' roles and the macro terrain pair table, with two adjacent regions never on one terrain. A region holding a home takes a town terrain. It returns each place's dominant.
- `place_map.py`: the place map a flood fill reads, the adjacency a label grid realises, and the repair once despeckle changed the grid. The flood gates every pair, with the entrance plan over every pair as its passages, its bands as wide as the caller asks. `front_cells` lists the tiles beside another place.
- `border_kinds.py`: the kind of each realised place pair (map-math 7). `draw_kinds` makes every unplanned pair closed, keeps a spanning forest of the planned pairs passable, and draws the rest from `PlaceStats.adjacency` by role pair.
- `streams.py`: `stream(seed, *parts)`, one stably seeded `Random` per part of a draw.
- `despeckle.py`: merges terrain patches too small or too thin for the tile art into the land around them.
- `gate_sites.py`: the Subterranean Gate sites, carved open on both levels and tunnelled to the nearest cavern.
- `levels.py`: `segment_places`, one zone per place with its sliver warnings, and `level_accents`, each level's accent patches.
- `macro.py`: the macro zone growth: the planned water mask, zones and corridors, drawn from `MacroStats`.
- `result.py`: `TerrainGrids`, the tunnel cells, `PlaceMap`, each level's places, their transition bands, the kind of each border and its `Passages`, `Segmentation`, and `Accents`, each level's accent patches, all of which `TerrainStep` publishes.
- `step.py`: `TerrainStep`, which draws both levels from its `TerrainModel` and segments each level into its places.
- `texture.py`: the boundary texturing, which samples the corpus Markov tables in a band around zone borders.
