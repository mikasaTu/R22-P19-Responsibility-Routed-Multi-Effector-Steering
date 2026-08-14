# Stage 2D: takeover capacity and desired responsibility

This subtree preserves the Stage 2C negative result and evaluates V2 without training
a policy.  It separates actual contribution, same-state donor-fade capacity, and an
independently stateful desired target.

Evidence tiers:

1. `analytic/`: perfect-model 4D allocator sanity (256 seeds, A0--A7).
2. `tasks/` + `capacity/`: actual active RoboTwin/SAPIEN donor-fade branches.
3. `scripts/run_local_causal_audit.py`: actual LR/L/R/ZERO contribution response.
4. `scripts/run_closed_loop_matrix.py`: 320 fresh-process diagnostic cells.

The capacity stress gate currently has no eligible stress.  Downstream runs are kept
as `INELIGIBLE_STRESS_OVERRIDE` evidence and cannot yield `ORACLE_V2_SUPPORTED`.
No PAI job or learned-policy training is created in this stage.

