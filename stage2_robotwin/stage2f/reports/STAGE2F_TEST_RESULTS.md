# Stage 2F Delivery-1 test receipt

- Environment: `/mnt/cpfs/zbl-cpfs-new/USERS/leon/deps/r22p19_stage2/venv/bin/python`
- Command: `python -m pytest -q stage2_robotwin/stage2f/tests`
- Stage2F result after independent-review hardening: `28 passed`
- Combined Stage2 through Stage2F result: `92 passed`, with two pre-existing
  SciPy SLSQP bounds-clipping warnings in Stage2D analytic tests.
- Covered: gamma=1 exact no-op, K1/K2 exception restoration, drive-property
  isolation, K3 non-soft receiver isolation, canonical float64 byte hashing,
  tied-rank Spearman, strict 48-cell matrix and five-null-per-seed validation,
  cross-gamma receiver/active-tape isolation, per-gamma G4, production cell-to-gate
  schema adaptation using both real smoke JSONs, full active-tape lineage, frozen
  matrix, and both 17-state calibration windows.
- PAI jobs: `0`
