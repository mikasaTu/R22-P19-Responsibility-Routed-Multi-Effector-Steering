# Mechanism reverse explanation

This document follows the runnable code and ablations only.  It does not propose a
new idea.

## 1. Why the analytic allocator improves target MAE

`analytic/operator.py` places `right - target * e_star` directly in the objective.
`receiver_share()` evaluates the projection of that same right effect onto `e_star`.
Consequently A4's large MAE improvement is principally solver compliance with a
metric-aligned target, not evidence that the target source is correct.  A5 and A6 lose
because they optimize a different target and are still scored against A4's desired
target.  The reviewers correctly identify this as a target-interface sanity check.

## 2. Why self-targeting does not transfer

A3 supplies `current_receiver` as its target.  The base was constructed with exactly
that projected share, so the target gradient is nearly zero.  Its mean contribution
movement is 0.000791.  This algebraic fixed point explains why routing toward current
responsibility cannot create a desired takeover; it is consistent with, but does not
replace, Stage 2C's empirical negative result.

## 3. Why internal-force regularization helps one metric and hurts another

A7 adds a penalty on the orthogonal component of left-minus-right effect.  Relative
to A4, it lowers the mean proxy from 0.018867 to 0.010580 because that exact component
is penalized.  It simultaneously worsens target MAE from 0.013723 to 0.015256 and is
worse than the no-op A1 in 3/256 cases.  The change is therefore a direct objective
trade-off, not an independent takeover benefit.

## 4. Why the active task fixes the quasi-static ceiling

`_active_item()` adds the same smooth sinusoidal world-frame displacement to both arm
targets, with zero offset at both overlap boundaries.  This raises mean object speed
from 1.44 to 5.77 mm/s and moving occupancy from 17.5% to 81.2%, while returning to the
unmodified expert trajectory before placement.  That code path explains the 10/10
task-success preservation and makes the overlap causally active.

## 5. Why the capacity score loses calibration

The capacity predictor averages translation, support, rotation, contact, drop, and
progress agreement at intermediate fade levels.  At 50 steps all branches retain
contact/support and all 146 labels are positive.  At 200 steps only 1/70 calibration
states is negative, so the composite AUROC is 0.478 while phase reaches 0.906.  The
loss is not numerical divergence: the score is dominated by easy support/contact
channels and the task provides almost no calibrated failure support.  Held-out AUROC
may look high when only two negatives exist; the zero eligible-stress gate prevents
that sparse statistic from being over-interpreted.

## 6. Why the first C13 closed-loop cell fails

The desired state starts at 0.1 and can move at most 0.08 per oracle node.  Persisted
capacity contains only five nodes, so the target stays below the release guard's 0.5
threshold over the relevant release requests.  The smoke cell blocks 420/420 donor
open commands, mean receiver target is 0.329, and final success is false.  This is a
time-scale mismatch between the sparse capacity refresh, hysteresis/slew state, and
release threshold.  It is retained without tuning before the formal matrix.

## 7. Why the formal full mechanism lowers success

The 320-cell matrix reproduces the same code-level failure, rather than an isolated
seed anomaly. C13 success is 1/5 clean, 2/5 T1, 1/5 T2, and 1/5 T3, versus 5/5
for C0 and C12 in every condition. C13 lowers the internal proxy from roughly
0.245 to 0.124--0.128, but its sparse capacity refresh and slew-limited state do not
cross the donor-release guard in time. The system keeps both effectors engaged,
changes the joint commands, and suppresses an orthogonal-differential proxy while
missing the required release/trajectory transition. The same frozen code path
explains the apparent metric gain and task loss.

## 8. Why correct-target controls do not separate

C8 correct, C9 swapped, C10 shuffled, and C11 time-shifted all remain at 5/5 in
each condition, so every pairwise success difference is 0 pp. The base task has a
success ceiling for this weaker operator family, and the effect perturbations do not
create a responsibility-specific failure region. These results therefore cannot
attribute success to the semantics of the correct target even though command
trajectories differ.

## 9. Why internal suppression is not a rescue mechanism

C14 changes the internal regularizer but its internal-proxy difference from C13 is
tiny and inconsistent across conditions (+3.69e-05, +7.22e-04, +2.01e-04,
-1.04e-05). It improves a few binary outcomes under T1/T2 but remains below the
5/5 base and conservation ceiling. This is neither robust internal suppression nor
evidence that takeover capacity is causal.

## Evidence boundary

Only analytic allocator results, actual SAPIEN donor-fade branches, actual active-task
replays, and their explicit controls are described.  Commanded allocation in the
closed-loop matrix is not called measured contribution; measured contribution is
reserved for the separate LR/L/R/ZERO local audit.
