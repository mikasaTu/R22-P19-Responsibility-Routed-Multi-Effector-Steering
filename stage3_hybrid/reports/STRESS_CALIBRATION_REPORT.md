# Stage3A stress calibration report

## Decision

`NO_INFORMATIVE_FAILURE_SPACE` with `accepted=false`.

All 14 single-factor conditions and all six frozen two-factor fallbacks were
executed on seeds 0 and 1, six modes, and two independent repeats. The complete
matrix contains 480/480 cells with zero runtime failures.

No condition met all four registered eligibility requirements. Fourteen
conditions had `base_success=1.0` and `oracle_success=1.0`; the candidate
disagreement there was caused by harmful modes, not by an improving mode. Five
conditions had `base_success=0.0`, `oracle_success=0.0`, and disagreement 0.0.
One condition had `base_success=0.0`, `oracle_success=0.0`, and disagreement
0.5. Thus every condition missed the registered `0.30 <= base_success <= 0.80`
range and every oracle gain was exactly 0.

Because fewer than two eligible stresses existed, the contract prohibits the
held-out matrix and bounded-horizon ranker. Those stages are gate-stopped, not
failed jobs and not omitted experiments. No PAI job was created.

