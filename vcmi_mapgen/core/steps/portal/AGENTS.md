# core/steps/portal/

## Map

- `rescue.py`: the target reachability check, `check_reach` over every level, and the portal rescue of unreachable zones. A crowded zone's far portal falls back to any free ground whose approach joins the zone's walkable web.
- `hoard.py`: `fill_hoards`, the prizes of each portal place. Each is priced by the effort to carry them home through the portal and drawn from its band's offer, its Pandora's Boxes among them. The guard at the near portal is its one guard. One prize tile is held open as the place's prize slot for `SetsStep`. A place no home reaches raises `UnreachedPlaceError`.
- `result.py`: `PortalResult`, the step's log and each portal place's price and prizes.
- `step.py`: `PortalStep`.
