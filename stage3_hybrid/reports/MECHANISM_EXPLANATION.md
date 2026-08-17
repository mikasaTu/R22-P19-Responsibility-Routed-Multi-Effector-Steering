# Mechanism reverse explanation (no new idea)

This is a code-and-ablation explanation of the observed increases and decreases;
it does not propose a new method.

## What the code actually changes

`M1/M2` take the donor position, velocity, and gripper from a future tape index
starting 100/50 steps before E4. `M3/M4` hold the entire donor pre-release
command for 50/100 steps, then replay a delayed donor suffix. `M5` holds that
pre-release donor command to the end. The receiver path is constructed once
from the condition and is byte-identical across modes. Therefore outcome
differences are identifiable as donor time-warp effects, not responsibility,
Jacobian, stiffness, receiver-command, or prefix effects.

## Why M1-M4 neither improve nor reduce task success

Across all 80 paired seed-condition-repeat groups, each of M1-M4 had exactly
the same success label as M0: 80/80 matches, zero rescues, zero harms. Their
global success rate was 0.70, identical to M0. They did change donor residual
duration in the intended direction (M1 374.2, M2 424.4, M0 474.5, M3 524.2,
M4 571.6 steps), proving that the commands were not no-ops. But this temporal
shift was not the limiting variable: stresses with an adequate receiver were
already at the success ceiling, while weakened-receiver stresses remained at
zero for every candidate. A donor-only time warp cannot restore receiver
tracking authority that its code never changes.

The modest disturbance changes did not cross a registered alternative gate.
For example, M3 reduced mean peak jerk from 220.41 to 212.98 (about 3.4%), far
below the 20% requirement; M4 increased mean slip from 0.08704 m to 0.08867 m.

## Why M5 reduces success

M5 rescued 0/80 groups and harmed 56/80. Relative to M0 it raised mean donor
residual duration from 474.5 to 695.5 steps, action deviation from 0 to 1.130,
peak jerk from 220.41 to 280.51, mean slip from 0.08704 m to 0.11524 m, and
drop rate from 0 to 0.05. Although donor final contact was usually already
lost, the held donor pose perturbed the object during transfer: among groups
where M0 succeeded, M5 changed the final object position by 0.02338 m on
average. RoboTwin success requires target alignment within 0.03 m in x/y and
0.01 m in z plus an open right gripper, so this accumulated trajectory error
is enough to invalidate terminal placement.

## Why high disagreement is not a positive upper bound

Many base-successful conditions had disagreement 1.0 only because M5 made an
otherwise successful episode fail. The privileged oracle merely avoided that
bad mode and stayed at the M0 ceiling; it never improved over M0. Conversely,
receiver-gain failures had no successful candidate. Candidate diversity was
therefore asymmetric—there was capacity to make behavior worse, but no
observed capacity to rescue a failure. That is exactly why eligibility and the
upper-bound premise were not established.

