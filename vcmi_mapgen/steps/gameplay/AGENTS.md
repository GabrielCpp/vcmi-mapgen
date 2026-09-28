# steps/gameplay/

## Map

- `step.py`: `GameplayStep` and the order it places objects in.
- `site.py`: where an object may stand in a zone: the shared level field, the cover index and each zone's spot search.
- `draw.py`: how many gameplay objects a zone holds, and which ones.
- `mines.py`: the gameplay corpus statistics, the player-zone pick and the economy helpers.
- `gate_pairs.py`: the Subterranean Gate pairs placed against the vegetated field.
- `shipyards.py`: which shipyard anchors are legal and which one each shore gets.
- `water.py`: the water-body objects and the seaport guarantee.
