# R22-P19 Phase-1 LIBERO Oracle Responsibility experiment report

## Decision

`LIBERO_SUBSTRATE_NO_GO`: 7/9 registered gates passed and 2/9 failed. ACT and
PAI were stopped by the registered signal gate. No training or inference job
was created.

This report contains successful expert-demonstration and simulator-privileged
counterfactual evidence only. It does not contain a learned responsibility
model, ACT result, pi0.5 result, world-model result, VLA generality claim,
closed-loop learned-policy result, or real-robot result. The original bimanual
Signal GO remains `not_tested`; `accepted=false`.

## Benchmark and intervention

- Primary: `libero_goal/put_the_bowl_on_the_plate`, demos 0-29.
- Gate-off control: `libero_goal/push_the_plate_to_the_front_of_the_stove`,
  demos 30-49.
- Primary groups: arm-pose coordinates 0-5 versus gripper coordinate 6.
- Authority stress: x coordinate versus y coordinate, gains `(1.30, 0.70)`
  and `(0.70, 1.30)`.
- Branches: FULL/AB, ARM/A, GRIPPER/B, and ZERO.
- Horizons: 5 and 10 control steps at 20 Hz; branch stride 5.

The Shapley-like attributions are:

```text
phi_A = 0.5 * [(y_A - y_ZERO) + (y_AB - y_B)]
phi_B = 0.5 * [(y_B - y_ZERO) + (y_AB - y_A)]
synergy = y_AB - y_A - y_B + y_ZERO
```

LIBERO's flat HDF5 state omits Python-side OSC controller buffers and
`PandaGripper.current_action`. The first smoke found this before any method
metrics were produced. The amended, frozen branch contract restores per-demo
MuJoCo state and model body poses, anchors OSC to the restored robot state,
and sets the gripper actuator target to the restored finger qpos. Exact
next-recorded-state replay is retained as a non-gating diagnostic; exact
repeated-branch identity is the determinism gate.

## Runtime provenance

- implementation source commit before compact result:
  `24d7cf3df4969275385ba977462c47e326211ae8`
- LIBERO commit: `8f1084e3132a39270c3a13ebe37270a43ece2a01`
- host: `dsw-925252-7796557db6-j84nn`
- Python: 3.8.13
- runtime UID:GID: `2254:2254`
- primary dataset SHA256:
  `e69528b0cf10dfc59b20698e12ec2affc03f3887309034d3eb74cac3ec929406`
- control dataset SHA256:
  `36b4e1bced49d2f4ff6b2fce6b1596a63978e14199e2513cd0df71e127bf47a6`
- frozen config SHA256:
  `c4d062b5a20db940ec086ba47a2e89346dc509695d7138e8733b9d80682e910a`
- formal run: `signal-v1-20260813`, completed 2026-08-13 01:33:18 CST

## Smoke and event audit

- dev14 unit tests: 3/3 passed.
- `smoke-v5-20260813`: exact repeated restore and repeated branch, ordered
  P1-P6 chain, implementation smoke passed.
- Full determinism sample: 9/9 repeated restores and 9/9 repeated branches
  had maximum flat-state error 0.
- 30/30 primary demos had an ordered P1-P6 chain.
- Numeric manual audit covered demos 0-9; 10/10 passed.

## Registered metrics

Passed:

- valid primary event fraction: `1.0 >= 0.80`
- phase AUC: `0.8388719653 >= 0.75`
- shuffled AUC p95: `0.5497561463 <= 0.60`
- transport minus grasp arm-share shift: `0.3031668592 >= 0.15`
- maximum relative conservation error: `3.0990244522e-14 <= 0.10`
- authority eligible count: `225 >= 20`
- authority-swap response accuracy: `210/225 = 0.9333333333 >= 0.80`

Failed:

- phase AUC over best-direction action-magnitude baseline:
  `0.0453244715 < 0.05`
- gate-off gripper activation: `47/414 = 0.1135265700 > 0.05`

The primary task contains 698 branch points, the gate-off control contains 414
branch points, and the authority stress contains 225 eligible points. The
phase signal and gain response are real in this substrate, but the registered
specificity and baseline-improvement requirements are not met.

## Stage stop

`evidence/signal-v1-20260813/ACT_PAI_SKIPPED.json` records:

- `pai_job_created=false`
- `job_id=null`
- `training_started=false`
- `inference_started=false`
- `cleanup_target_count=0`

This is a scientific gate stop. It must not be reported as a PAI failure.

## Next test

1. Separate finger-joint response from object-level causal motion so the push
   gate-off activation falls to at most 0.05.
2. Add a matched-action-magnitude or residualized baseline without lowering
   the registered threshold.
3. Repeat the same 30+20-demo gate under a new run ID.
4. Start ACT on PAI only if all nine gates pass.
5. Even after a LIBERO pass, test real bimanual authority swapping before
   making the original R22-P19 claim.
