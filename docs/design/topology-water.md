# Topology water in `generate`

I saw the existing terrain code and the prototype before writing this note. Section 1b lists
every design decision the prototype carries as a claim.

## 1. Problem

A player opening a generated map with water sees ponds scattered over one land mass. They
never see a coast that frames a continent, a sea that parts islands, or an inland lake.

Done looks like this. `uv run python -m vcmi_mapgen.cli generate --seed N` draws, for each
seed, a water share, a share of water on the map edge and a land-mass count from one corpus
map. The map it writes meets the water share within 0.02 and the edge share within 0.03. A
map drawn with k land masses has at least k-1 masses above 5% of the land, and water parts
every pair of them. Same seed, same map.

Out of scope: water underground, boats and shipyards (the gameplay water placement owns
them), the HotA corpus, and wider seas between islands.

## 1b. Claims

1. Water comes from the map's topology, not from noise. (user)
2. `--water-mode` stays the selector. (agreed design)
3. The golden hashes are rebuilt for the new default. (agreed design)
4. A logistic model fitted on corpus tiles gives each tile's odds of water from the place
   geometry, and two neighbour terms give its odds from the water around it. (prototype)
5. A Gibbs sampler draws the mask, with two multipliers that steer it to the target water
   share and edge share. (prototype)
6. The graph splits into k masses, and the tiles where two masses meet are water before
   sampling starts. (user: "Let do that")
7. Each target triple is one corpus map's (water share, edge share, mass count). (prototype)
8. A soft pull keeps the water away from every place anchor. (prototype)

## 2. Parts and concepts

Level 1:

- **Surface form**: decides where the surface is land and where it is water, and lays the
  places out on that land. It never knows terrain identity or paint.
- **Water reading**: measures water against place geometry, the same way on a corpus map
  and on a generated one. It never knows how a map was made.
- **Water fitting**: reads the corpus once and stores the model and the targets. It never
  knows the sampler.
- **Assembly**: picks the surface form variant from the user's water mode. It never knows
  how a variant works.

Flow: assembly picks the form. At generation time the surface asks the form for its graph
and layout, then paints. Fitting runs offline in `mine-stats` and uses the reading. The form
uses the reading's features and the fitted priors.

### Surface form

| Concept | Owns | Never knows |
|---|---|---|
| Surface form (role) | answering "the place graph and its layout, water labelled -1" | which variant runs |
| Noise form (variant) | today's order: noise land mask first, then the graph and the layout on it | the fitted water model |
| Topology form (variant) | the new order: the graph and layout on all land first, then water | the noise mask |
| Water target | drawing one (share, edge share, mass count) triple | the sampler |
| Mass partition | splitting the graph's places into k masses, homes first, by area | tiles |
| Strait | the tiles where two masses meet, forced to water | why the masses differ |
| Water sampler | drawing the mask that meets the target, with forced and protected tiles | place roles |

### Water reading

| Concept | Owns | Never knows |
|---|---|---|
| Water features | each tile's static features and neighbour features from place centres, radii, masses and towns | where the places came from |
| Water summary | one map's (share, edge share, mass count) | features |

### Water fitting

| Concept | Owns | Never knows |
|---|---|---|
| Water fit | the logistic coefficients, full and static only, by IRLS | the sampler |
| Water priors | the frozen coefficients and the corpus target triples | the corpus files |

## 3. Invariants

- The forced strait tiles are water in the finished mask. The water sampler owns it.
- No place anchor is water. The water sampler owns it.
- Every gate site is land when the map has an underground. The topology form owns it.
- The same seed draws the same mask. The water sampler owns it, through one seeded stream.

## 4. Forces and patterns

- Two interchangeable ways to form the surface, picked by the user: the **surface form**
  role with the noise and topology variants. `PlacesTerrain` takes one in its
  constructor, as `VegetationStep` takes a `Sampler`. A new mode adds one variant and one
  line in assembly.
- The corpus and the generator measure the same features: one module in `core/reading/`
  both sides import.
- The coefficients change when the corpus changes: a frozen prior value, mined by
  `mine-stats --only water` into `data/pp/water.json`.
- Everything else is a plain function.

Claims 1, 4, 5, 6, 7 and 8 come from the forces above and the prototype results. Claim 2
holds: `--water-mode` gains the value `topology` and keeps `none`, `normal` and `islands`
on the noise form. Claim 3 holds: `topology` becomes the default, and `make golden-update`
rebuilds the hashes.

## 5. Mapping onto the existing system

- Surface form: **new** role in `core/steps/terrain_gen/coastline.py`. The noise variant is
  the body of today's `ground`, `draw_graph` and `lay_out` calls in `places.surface`,
  moved out unchanged. The topology variant goes in `core/steps/terrain_gen/water.py` with
  the target, the partition, the strait and the sampler.
- Water features and summary: **new** in `core/reading/water.py`.
- Water fit: **new** `corpus/mine/water.py`. Water priors: **new** `core/priors/water.py`,
  with `corpus/water.py` to load and save, and a `water` field on `Priors`.
- Assembly: **reshape**. `cli/steps.py` `build_steps` builds the form from
  `StepConfig.water_mode`. The CLI default changes from `normal` to `topology` in
  `generate` and `render-vegetation`.
- The `markov` terrain model reads `water_mode` too, and it has no place graph. It keeps
  the noise water: `topology` reaches the noise land mask as `normal` (A2).
- Gameplay already places a shipyard on every island above 50 tiles
  (`core/placement/water.py`), so a hero can cross each strait (A1).

## 6. Slices

1. Priors and reading: mine `data/pp/water.json`, load it into `Priors`. Done when
   `mine-stats --only water` writes it and the loader test reads it back.
2. The topology form behind the role, the default in the CLI. Done when `generate --seed 1
   --subterrain` writes a full map with the new water, and `make check` passes after
   `make golden-update`.

## 7. Assumptions

1. **Assumption**: the gameplay shipyard rule makes every island reachable. **Decided**: no
   change to gameplay. **Basis**: `core/placement/water.py` seaport guarantee, and the
   prototype batch, whose maps all report "playable". **If wrong**: section 1 scope, slice 2.
2. **Assumption**: nobody runs `--terrain markov` expecting topology water. **Decided**:
   markov keeps the noise water under every mode. **Basis**: the places model is the
   default. **If wrong**: section 5 markov line.
3. **Assumption**: one corpus fit serves every map size. **Decided**: features scale with
   place radius and map half side. **Basis**: the fit pools 36 to 144 tile maps. **If
   wrong**: water features.
