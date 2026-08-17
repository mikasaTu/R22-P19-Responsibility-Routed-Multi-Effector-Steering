# Stage3A test results

- Stage3A test suite: **24/24 passed**, including all 12 explicitly named mandatory contracts.
- Historical Stage2 pytest suite: **64/64 passed**, with two pre-existing SciPy bound-clipping warnings.
- Single-factor runtime matrix: **336/336 complete, 0 failed**.
- Two-factor runtime matrix: **144/144 complete, 0 failed**.
- Runtime receipt audits: **16/16 checks passed** across the two matrices.
- Formal result count: **480** cells; every cell has `accepted=false` and `pai_job_created=false`.

The mandatory Stage3A tests cover receiver invariance, M0 no-op, paired donor
arm/velocity/gripper shifts, prefix identity, fresh-process/no-snapshot flags,
outcome-independent mode definitions, feature leakage, lexicographic oracle,
wrong mapping, missing-cell fail-closed behavior, decision vocabulary, and the
exact candidate/stress library.
