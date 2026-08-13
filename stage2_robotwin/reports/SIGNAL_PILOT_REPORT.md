# R22-P19 Stage 2A oracle signal pilot report

Status: **PILOT_LOCALIZED_SIGNAL_FORMAL_PENDING**

Machine status: `PILOT_ONLY_INSUFFICIENT_N`

Date: 2026-08-13

Acceptance flag: `accepted=false`

## Outcome first

The real RoboTwin dual-arm counterfactual branch pipeline now runs end to end,
but the preregistered Stage 2A audit is not complete and no formal
`SIGNAL_STRONG`, `SIGNAL_PARTIAL`, `SIGNAL_NEEDS_THREE_WAY`, or `SIGNAL_WEAK`
label is assigned.

The ordinary expert-action gain, delay, friction, compliance, and geometric
direction/null profiles mostly failed to create an observable object-authority
swap at H=5/10. A bounded diagnostic that combined Jacobian-aligned actions
with a strong `0.05` compliance scale on the non-dominant arm did create a
localized swap around the release transition. In the dense one-seed run:

- 46 physical states were branched at H=5 and H=10;
- ordinary direction/null had `0/92` valid paired object-authority swaps;
- compliance-assisted direction/null had `21/92` valid paired swaps,
  representing 12 unique physics steps from step 3850 through 4150;
- on those 21 valid pairs, oracle direction accuracy was `21/21 = 1.0`;
- all 21 observations come from one expert episode and one narrow transition
  window, and the compliance setting is diagnostic rather than formal.

This is localized positive mechanism evidence and a useful intervention-design
finding. It is not a paper result, not a deployable estimator, and not evidence
that the complete responsibility-conserving operator improves control.

## What was implemented

- Real SAPIEN snapshots and deterministic restore of articulation, actor,
  drive-target, velocity, sleep, and normalized gripper state.
- Four branches from an identical state: `LR`, `L`, `R`, and `ZERO`.
- Neutral arm command: current measured joint position plus zero target
  velocity; gripper closure and low-level drive mode are preserved.
- Vector outcomes for translation, rotation, twist, support, progress, slip,
  drop, and contact retention.
- Separate Shapley, support, progress, harmful, slip, and joint-synergy
  channels, plus an unconstrained three-channel `(rho_L, rho_R, rho_joint)`
  representation.
- Paired gain, delay, friction, compliance, geometric direction/null, and
  diagnostic compliance-assisted direction/null profiles.
- An intervention-validity gate that refuses to score oracle accuracy unless
  the nominal left and right profiles actually produce positive, dominant
  object motion in the intended task direction.

## Pilot lineage

| Run | Change | Key result |
| --- | --- | --- |
| `pilot-v1` | Initial branch integration | 50/50 paired comparisons tied; exposed neutral-action error |
| `pilot-v2-neutral-qpos` | Neutral uses measured qpos | 1/230 informative comparison; insufficient |
| `pilot-v3-horizon-sensitivity` | H=5/10/25/50 | 459/460 ties; longer horizon did not fix the intervention |
| `pilot-v4-direction-null` | 4 mm Jacobian direction/null actions | FK direction cosine about 0.99998+, but 0/10 valid object swaps |
| `pilot-v5-compliance-assisted` | Add 0.05 non-dominant compliance | 2/10 valid pairs at one transition state; oracle 2/2 |
| `pilot-v6-dense-transition` | Direction-only sampling every 25 steps | 21/92 diagnostic valid pairs over 12 steps; oracle 21/21 |

Every run is retained, including the invalid early assumptions. The latest
machine-readable result is
[`pilot-v6-dense-transition/signal_metrics.json`](../results/oracle_signal/pilot-v6-dense-transition/signal_metrics.json).

## Why the ordinary profiles were uninformative

The expert handover establishes real two-gripper overlap, but during most of
that interval it does not command both hands to drive the block. H=5/10 base
branches had nonzero object-motion effect at only 6/23 sampled states, whereas
the negative-slip channel was nonzero at 19/23 states. Extending the horizon
to 25 and 50 steps left the motion effect nonzero at 6/23 states and did not
make the paired authority profiles informative.

The geometric direction command itself was correct at the robot kinematics
level: requested 4 mm displacements had forward-kinematics direction cosine
between approximately 0.99998 and 0.999997 in the inspected states. Under
dual contact, however, the other stiff arm often constrained the object, so a
TCP action aligned with the task direction did not necessarily become an
object-driving action. This is an intervention-validity failure, not a
negative oracle result.

## Reconstruction and evidence checks

- Every stored Shapley channel reconstructs its LR-minus-ZERO effect; maximum
  recorded reconstruction error in the latest pilot is at numerical precision.
- The dense pilot contains 460 JSONL records across 46 states and two horizons.
- The diagnostic valid-pair oracle result is computed only after the
  independent positive-dominance intervention gate.
- Tie-aware accuracy scores a zero margin as 0.5 and separately reports the
  informative-only accuracy; ties are not mislabeled as incorrect swaps.
- Shuffled orientation remains approximately 0.5 in the pilot analyzer.

## Evidence boundary and missing work

Formal Stage 2A requires at least 30 successful and 20 perturbed
`handover_block` episodes, 20 `lift_pot`, 20 `pick_dual_bottles`, and 20--30
`handover_mic` episodes. Current progress is 1/30, 0/20, 0/20, 0/20, and
0/20--30 respectively. Therefore:

- no formal signal label is assigned;
- joint synergy has not been validated on `lift_pot`;
- shared-object router specificity has not been validated on
  `pick_dual_bottles`;
- cross-geometry transfer has not been validated on `handover_mic`;
- mismatch prediction for jerk/slip/drop has not been estimated across
  episodes;
- no operator, ACT policy, closed loop, or real robot was evaluated.

## ACT and PAI decision

ACT training and inference were not started because the real Stage 2A signal
audit is still a bounded one-episode pilot. No PAI `CreateJob` call was made.
An anticipatory PAI preflight also failed closed because the shared registry
was dirty and its live helper hash did not match the active skill contract;
see [`PAI_PREFLIGHT_BLOCK.json`](PAI_PREFLIGHT_BLOCK.json). This infrastructure
condition is separate from the scientific pilot result.

## Recommended next experiment

Freeze a contact-aware intervention that can generate valid swaps without the
extreme 0.05 compliance confound. Then run 3--5 seeds in the 3850--4150-style
relative E4 window before committing to the complete 30+20 episode audit.
Only after the ordinary intervention is valid across seeds should the control
tasks and ACT/PAI stage proceed.
