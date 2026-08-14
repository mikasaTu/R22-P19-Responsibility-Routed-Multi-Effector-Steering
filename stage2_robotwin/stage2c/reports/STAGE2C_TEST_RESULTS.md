# Stage 2C Test and Verification Receipt

Date: 2026-08-14

Host: `dev14`

Runtime: `/mnt/cpfs/zbl-cpfs-new/USERS/leon/deps/r22p19_stage2/venv/bin/python` (Python 3.10.19)

## DONE

- Stage 2C unit/regression suite: `15 passed in 2.20s`.
- Final combined Stage 2/2B/2C suite after publication formatting:
  `52 passed in 11.01s`.
- In-memory source compilation: `33` Python files compiled without writing
  bytecode.
- JSON parse audit: all compact Stage 2C JSON artifacts parsed successfully.
- Formal decision audit: 448/448 finite cells; exact C0/C11 null parity;
  identical same-seed/same-condition prefixes; equal oracle budgets.

Commands:

```bash
cd /mnt/cpfs/zbl-cpfs-new/USERS/leon/code/R22-P19-Responsibility-Routed-Multi-Effector-Steering

TMPDIR=<fresh-cpfs-temp> PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. \
  /mnt/cpfs/zbl-cpfs-new/USERS/leon/deps/r22p19_stage2/venv/bin/python \
  -m pytest -q -p no:cacheprovider stage2_robotwin/stage2c/tests

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. \
  /mnt/cpfs/zbl-cpfs-new/USERS/leon/deps/r22p19_stage2/venv/bin/python \
  -m pytest -q -p no:cacheprovider stage2_robotwin/tests \
  stage2_robotwin/stage2b/tests stage2_robotwin/stage2c/tests
```

The Stage 2C suite includes a regression for the expert-tape manifest schema:
capture completeness and event validity are derived from each tape's
`attempts.json`, rather than assumed to be top-level tape-metadata fields.

## KEY RESULT

Tests verify the exact-null substrate, tape round trip and capture gate,
natural responsibility statistics, soft authority semantics, signed/joint
state, temporal filtering, 1D/4D operator constraints, stress selection,
matrix orchestration, interruption recovery, and final decision gates. The
machine decision remains `RESPONSIBILITY_MECHANISM_NOT_SUPPORTED`; tests do
not convert a negative scientific result into acceptance.

## LIMITATION

Unit tests and compact-artifact audits are code/runtime checks. The simulator
claim comes only from the retained formal CPFS runs and episode-level analysis;
neither test success nor finite JSON is policy, deployment, or real-robot
evidence.

## NEXT

ACT, PAI training, deployable responsibility estimation, and extra tasks stay
blocked by `reports/CURRENT_STAGE2C_DECISION.json`.
