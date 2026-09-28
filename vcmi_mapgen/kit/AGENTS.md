# kit/: step-independent helpers

Code here serves several steps or tools and knows nothing about the pipeline order. No
module here has its own `__main__`.

## Map

- `paths.py`: `project_root()`, the repository root.
- `pp_cache.py`: how a `data/pp/` statistics file is read and written, and the error when one is missing.
