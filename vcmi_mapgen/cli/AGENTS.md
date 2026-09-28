# cli/: the composition root

Every command a person runs starts here. `python -m vcmi_mapgen.cli <subcommand>` parses the
arguments in `__main__.py` and calls one module per subcommand.

## Map

- `__main__.py`: argument parsing and the subcommand table.
- `audit.py`: the `audit` subcommand. It reports the corpus objects the generator cannot reproduce, or prints the gameplay densities.
- `corpus_match.py`: the `corpus-match` subcommand. It generates maps from `build_steps` and prints the corpus comparison.
- `extract_vmap.py`: the `extract-vmap` subcommand. It regenerates `maps_vmap/` from the `.h3m` corpus.
- `generate.py`: the `generate` subcommand: pipeline run, overlays and renderers.
- `macro_preview.py`: prints the macro statistics and renders one macro terrain grid to a PNG.
- `render_sprites.py`: the `render-sprites` subcommand. It renders one `.vmap` with the real H3 sprites.
- `settings.py`: `Settings`, the one place that reads `os.environ` and `sys.platform`, and `open_install`, which finds the VCMI install or exits naming `VCMI_HOME`.
- `steps.py`: `build_steps`, the one step list, and the `--stop-after` names.
- `veg_experiment.py`: the M1 experiment. It samples vegetation on a real corpus zone and
  compares the run lengths with the corpus.
