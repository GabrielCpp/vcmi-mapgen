# core/steps/treasure/

## Map

- `price.py`: `price_places`, each sealed loot zone's effort in hero-days from the nearest home and its band. A place no home reaches raises `UnreachedPlaceError`.
- `fill.py`: `fill_loot_zones`, the treasure inside each sealed loot zone. Each place gets one headline artifact drawn from its band's basket, on the free tile farthest from its opener, before the rest of the fill. The headline tile is held open as the place's prize slot for `SetsStep`. The band's Pandora's Boxes stand on the next deepest tiles.
- `islands.py`: the islands, land places no home reaches on foot that a hero reaches by boat. `IslandFill.guard` places their guards first. `IslandFill.fill` then prices each island on the effort map that sees those guards and places at most three prizes beside each guard from its band's offer. Each island holds one prize tile open as its prize slot for `SetsStep`. A guard left with no prize is dropped.
- `result.py`: `TreasureResult`, each gated place's and island's price and prizes.
- `step.py`: `TreasureStep`.
