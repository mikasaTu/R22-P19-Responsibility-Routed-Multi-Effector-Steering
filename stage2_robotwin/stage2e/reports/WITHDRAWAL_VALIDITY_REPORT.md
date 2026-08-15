# Stage 2E Withdrawal Validity Report

## DONE

- Frozen predecessor: `05600234df39367424fcb8036533b5e111d2a0aa`.
- Executed the preregistered immediate Stage 2E scope on dev14: conformance audit,
  true motion/support/rotation/retention withdrawal, fresh-scene order/null audit,
  and three-episode withdrawal monotonicity.
- Completed `120/120` physical branches: 3 seeds x 4 channels x 5 fade levels x
  2 independent repeats. Every branch used a fresh process and fresh RoboTwin scene,
  replayed from episode start, and did not restore a snapshot.
- Used one physical GPU (`CUDA_VISIBLE_DEVICES=2`) with two concurrent workers. No
  PAI job, VLA training, ACT/pi0.5 inference, learned estimator, allocator, or
  closed-loop policy evaluation was run.

## WHAT CODE ACTUALLY EXECUTED

The arm-channel withdrawal path did not change stiffness. RoboTwin/SAPIEN exposes
diagonal joint-drive impedance but not Cartesian-axis impedance. The implemented
object-following fallback therefore:

1. projected the expert donor joint-position error through the live Jacobian;
2. selected translation along the object motion axis, translation along vertical,
   or rotation about vertical;
3. multiplied only that selected twist component by `fade`;
4. mapped the remaining twist back through a Jacobian pseudoinverse to a donor joint
   target;
5. left the receiver command byte-identical.

Retention withdrawal interpolated the real donor gripper command continuously toward
RoboTwin's open target. Contact impulse and torque were measured per hand from live
SAPIEN contacts and projected into the object task frame. Runtime receipts record the
actual method path, action modifications, solver-call count, and receiver-command hash.

This code is not the frozen full V2 mechanism. It contains no counterfactual capacity
classifier, desired-responsibility state machine, common 4D constrained allocator,
internal-wrench objective, release guard, or deployable closed loop.

## KEY RESULT

Machine decision: **`WITHDRAWAL_NOT_IMPLEMENTABLE`** (`accepted=false`). All 12
seed-by-channel groups were complete, but `0/12` satisfied all gates.

| Channel | Median effect at fade=0 | Median effect at fade=1 | Per-seed fade=0 / fade=1 | Main failed gate |
|---|---:|---:|---:|---|
| motion | 0.025546 | 0.025551 | 1.0003, 1.0001, 0.9998 | selected effect was not <=10% |
| support | 0.018136 | 0.018137 | 1.0000, 0.9995, 1.0001 | selected effect was not <=10% |
| rotation | 0.008412 | 0.008407 | 1.0006, 1.0000, 1.0021 | selected effect was not <=10% |
| retention | 0.002458 | 0.037034 | 0.0651, 0.0664, 0.0653 | non-target effects and contact-duration gate failed |

Arm command changes were real and smoothly decreased with fade. Median donor joint
target modification at fade 0 was 0.006887 rad for motion, 0.006105 rad for support,
and 0.014759 rad for rotation; it was numerically zero at fade 1. Nevertheless, donor
contact persisted for 100% of the 60-step horizon and the measured selected contact
effect stayed at essentially 100% of baseline for all three arm channels.

Retention opening reduced the selected impulse-norm proxy to about 6.5% of baseline
and ended without donor contact in every fade-0 repeat, but contact persisted for
63.3% of the horizon rather than <=10%. More importantly, motion and support fell to
about 6.3-6.5% and rotation to 6.5-11.1% of baseline, violating the >=80% preservation
gate for all non-withdrawn channels.

The isolation controls passed: every seed-by-channel group had one receiver-command
hash across all fades and repeats; duplicate relative error was exactly zero; all
fades had two fresh repeats. These controls show the negative result is not explained
by receiver command drift, launch order, or duplicate noise.

## WHAT WAS FALSIFIED

1. The live-Jacobian target-projection fallback is not a valid physical
   channel-specific withdrawal operator in this contact regime. A kinematic target
   edit did not remove the corresponding contact-wrench component.
2. Full donor gripper opening is causally effective, but it is not channel-specific:
   breaking the grasp removes nearly all donor wrench channels together.
3. Therefore motion/support/rotation/retention cannot currently serve as independently
   manipulable responsibility coordinates in this RoboTwin implementation.
4. The preceding conformance audit independently returned `CONFORMANCE_NO_GO`: five
   mandatory full-mechanism checks were absent. The physical diagnostic cannot repair
   or override that gate.

## LIMITATION

- This is a three-episode, 60-step, privileged-simulator diagnostic on
  `handover_block`, not a policy benchmark or deployable controller result.
- Contact impulses are per-step simulator impulses, not calibrated force/torque sensor
  measurements. Absolute magnitudes should not be compared to hardware forces.
- The arm withdrawal fallback removes a commanded pose-error component, not true
  Cartesian impedance or achieved wrench. Contact constraints, joint servo feedback,
  and the other arm can therefore restore the same contact load.
- The exact-zero duplicate error is expected from deterministic replay and does not
  establish robustness to stochastic dynamics.
- The optional cuRobo/pytorch3d imports were unavailable; the requested and executed
  planner was `mplib_screw`, and all 120 branches completed.

## NEXT

The frozen decision rule stops the V2 direction here. Do not implement the capacity
classifier, allocator, learned estimator, ACT pilot, PAI training, or closed-loop
claims under this mechanism. Any future work would require a separately authorized,
newly preregistered mechanism rather than interpreting these diagnostics as support.

