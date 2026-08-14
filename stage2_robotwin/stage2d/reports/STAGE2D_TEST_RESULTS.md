# Stage 2D test and publication receipt

## dev14 combined test

Command:

```bash
PYTHONPATH=. /mnt/cpfs/zbl-cpfs-new/USERS/leon/deps/r22p19_stage2/venv/bin/python \
  -m pytest -q stage2_robotwin/tests stage2_robotwin/stage2b/tests \
  stage2_robotwin/stage2c/tests stage2_robotwin/stage2d/tests
```

Result on 2026-08-15: **59 passed, 2 warnings in 6.82 s**.

Both warnings are retained SciPy SLSQP `x outside bounds` clipping warnings in
the Stage 2D analytic tests. There were no failures or errors.

## Formal experiment completion

- analytic: 256/256 seeds, A0--A7;
- active task: 10/10 seeds plus fresh-process seed-2 repeat;
- local causal: 225 method-state evaluations, 900 SAPIEN branches;
- closed loop: 320/320 fresh-process cells, zero runtime failures;
- PAI jobs: zero, by the frozen oracle-policy gate.

This receipt does not upgrade the negative scientific decision. See
`CURRENT_STAGE2D_DECISION.json`.
