# cli/: the composition root

Every command a person runs starts here. `python -m vcmi_mapgen.cli <subcommand>` parses the
arguments in `__main__.py` and calls one module per subcommand.

## Map

- `__main__.py`: argument parsing and the subcommand table.
- `audit.py`: the `audit` subcommand. It reports the corpus objects the generator cannot reproduce, or prints the gameplay densities.
- `corpus_match.py`: the `corpus-match` subcommand. It generates maps from `build_steps` and prints the corpus comparison.
- `extract_vmap.py`: the `extract-vmap` subcommand. It regenerates `data/corpus/vmap/` from the `.h3m` corpus. `--h3m-dir` and `--out-dir` convert another folder, `--mods` enables mods such as `hota`, whose map format renames the objects of a HotA map, and `--png-dir` renders each converted map.
- `generate.py`: the `generate` subcommand: pipeline run, overlays and renderers.
- `mine_stats.py`: the `mine-stats` subcommand: which corpus statistics exist and the one
  pass that rebuilds every `data/pp/` file.
- `macro_preview.py`: prints the macro statistics and renders one macro terrain grid to a PNG.
- `patch_report.py`: the `patch-report` subcommand. It generates maps, reads their small enclosed patches and those of every corpus map with `core/reading/patches.py`, and prints the cover, the share of patches with a counted object, the purpose mix and the maps with a dragon dwelling side by side.
- `readings.py`: the `readings` subcommand. It generates maps with each terrain model, reads them and the corpus maps of the same side with `core/reading/vector.py`, prints each reading's corpus median and quartiles beside each model's median, and prints the `core/reading/verdict.py` switch rule's answer against the default model.
- `render_vmaps.py`: renders every `.vmap` of a folder to PNGs, each level with the map's own tile strings, for `extract-vmap --png-dir`.
- `render_sprites.py`: the `render-sprites` subcommand. It renders one `.vmap` with the real H3 sprites.
- `settings.py`: `Settings`, the one place that reads `os.environ` and `sys.platform`, and `open_install`, which finds the VCMI install or exits naming `VCMI_HOME`.
- `steps.py`: `StepConfig`, what one generation asks for, and `build_steps`, the one step
  list built from the priors and that config. `TERRAIN_MODELS` builds each terrain model from the surface form `SURFACE_FORMS` names per water mode. `DEFAULT_TERRAIN` is `places` and `DEFAULT_WATER` is `topology`. `CONTENTS` and `ROADS` pick the content planner and the road layer per terrain model.
- `veg_report.py`: prints one terrain's mined vegetation statistics.
- `veg_experiment.py`: the M1 experiment. It samples vegetation on a real corpus zone and
  compares the run lengths with the corpus.
