# core/steps/sets/

## Map

- `slots.py`: `price_slots`, each held prize slot's effort in hero-days from the nearest player town, its band and that home.
- `deal.py`: the deal. `set_quota` gives one set per 72x72 tiles over both levels, at least one. `dealable` keeps the sets whose parts the catalog resolves, minus the water sets on a dry map. `deal_sets` picks sets at random and gives each part one slot in the top two bands, round-robin over the homes, the highest-tier part on the costliest slot.
- `stand.py`: `stand_all` places every part of a dealt set or none of them, then fills each slot no set took with its place's basket artifact, else a resource pile.
- `result.py`: `SetsResult`, each placed set with its parts and their bands, and the count of slots filled and left empty.
- `step.py`: `SetsStep`.
