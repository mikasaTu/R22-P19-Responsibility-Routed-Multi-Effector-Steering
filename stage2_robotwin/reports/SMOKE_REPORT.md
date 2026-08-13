# R22-P19 Stage 2 RoboTwin bimanual smoke report

Status: **DONE_WITH_BOUNDARIES**

Date: 2026-08-13

Acceptance flag: `accepted=false`

## Outcome first

The required `handover_block` smoke is complete. Ten successful RoboTwin 2.0
expert episodes passed all of the following checks:

- task-level success;
- ordered E0--E6 event chain;
- visible donor-only, bimanual-overlap, donor-release, and receiver-only stages;
- readable contact actor IDs, impulses, object pose, and object twist;
- deterministic replay from the E3 snapshot for ten physics steps;
- unilateral gain, delay, and gripper-friction mutation capability.

This proves that the selected simulator substrate can express and audit a real
two-arm handover. It does **not** yet prove that counterfactual responsibility
contains useful signal, that an operator improves control, or that anything is
deployable. No learned policy was trained or evaluated.

## Frozen runtime contract

| Item | Frozen value |
| --- | --- |
| R22-P19 base commit | `28f835af5a54a50ab7e3c9e1ad9d763356ad8c60` |
| RoboTwin commit | `266f3aadf505a4f7fe9af0faa41a20f5f47cd123` |
| XPolicyLab gitlink | `c37109c500be67d0dea6b36bf7337bbd26e763cd` |
| Task/config | `handover_block` / `demo_clean` |
| Embodiment | Aloha-AgileX, real dual-arm articulation |
| Physics/trace | 250 Hz / 250 Hz |
| Video | observer RGB, 10 Hz target with event frames |
| Learned-policy action contract | 14-D: L arm 6, L gripper 1, R arm 6, R gripper 1 |
| Expert low-level action | joint position and velocity drive targets |
| Planner | explicit `mplib_screw` fallback |
| Python / NumPy | 3.10.19 / 1.26.4 |
| SAPIEN | 3.0.0b1 |
| PyTorch | 2.4.1+cpu; not used for simulation dynamics |
| Renderer device | dev14 A800 GPU3 during the completed run |

The Aloha asset's upstream configuration defaults to CuRobo, but the dev14
runtime did not have a valid CuRobo/PyTorch3D installation. RoboTwin itself
leaves `mplib_screw` as its non-CuRobo Aloha option. The adapter fails closed
for unknown planners and records one important semantic deviation: MPLib
0.2.1 cannot apply CuRobo partial-pose hold vectors. Exactly two such requests
were counted in every successful episode. Therefore this smoke establishes the
MPLib execution substrate, not exact CuRobo-expert parity.

The complete source and asset provenance is in
[`source_manifest.json`](../source_manifest.json).

## Episode results

The runner searched deterministic seeds until it accumulated ten episodes
that were both task-successful and event-valid. It attempted 11 seeds; seed 4
was preserved as a failure. Consequently `10/11` is a seed-search yield, **not**
an unbiased success-rate estimate.

| Episode | Seed | E0 | E1 | E2 | E3 | E4 | E5 | E6 | Result |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 0 | 0 | 1148 | 3411 | 3411 | 3425 | 4083 | 4555 | 4569 | PASS |
| 1 | 1 | 793 | 2738 | 2738 | 2752 | 3400 | 3884 | 3898 | PASS |
| 2 | 2 | 1038 | 3255 | 3255 | 3269 | 3927 | 4423 | 4437 | PASS |
| 3 | 3 | 757 | 2880 | 2880 | 2894 | 3550 | 4061 | 4075 | PASS |
| 4 | 5 | 783 | 2982 | 2982 | 2996 | 3673 | 4184 | 4198 | PASS |
| 5 | 6 | 870 | 2892 | 2892 | 2906 | 3575 | 4081 | 4095 | PASS |
| 6 | 7 | 897 | 2797 | 2797 | 2811 | 3472 | 3958 | 3972 | PASS |
| 7 | 8 | 1048 | 3178 | 3178 | 3192 | 3903 | 4388 | 4402 | PASS |
| 8 | 9 | 1021 | 3386 | 3386 | 3400 | 4081 | 4585 | 4599 | PASS |
| 9 | 10 | 972 | 3050 | 3050 | 3064 | 3732 | 4237 | 4251 | PASS |

E1 and E2 coincide because the receiver's first detected contact produces a
simultaneous-contact state in the same discrete physics step. E2 precedes E3
strictly, and all later stage boundaries are strictly ordered.

Seed 4 reached donor-only contact (E0 at step 1803), then the expert planner
failed before receiver contact at step 3020. Its partial trace and video are
retained and it was not counted among the ten passes.

## Manual visual audit

All ten E0--E6 montages were opened and inspected individually. Every montage
showed:

1. the left donor alone holding the red block at E0;
2. both grippers visibly surrounding the same block at E1--E3;
3. the donor opening while the receiver still held the object at E4;
4. the donor disengaged/retracting and the right receiver alone holding the
   object at E5--E6.

Visual verdict: **10/10 PASS**. The machine-readable record is
[`smoke_manual_audit.json`](smoke_manual_audit.json); the montages are under
[`smoke_assets/event_montages`](smoke_assets/event_montages).

## Snapshot/restore audit

An initial implementation called `Scene.unpack_poses()` and then restored
articulation generalized state. That briefly imposed inconsistent articulation
link poses and produced large replay divergence. This failed attempt is
preserved in the [smoke result lineage](../results/smoke/README.md).

The corrected snapshot captures and restores:

- every articulation's qpos/qvel and root pose/twist;
- every active joint's drive position/velocity target;
- every dynamic rigid actor's pose, linear/angular velocity, and sleep state;
- normalized left/right gripper bookkeeping.

It restores articulation state through the PhysX articulation APIs and dynamic
actors through their rigid-body APIs; it deliberately does not unpack every
articulation-link entity pose.

For each successful episode, two replays from the E3 snapshot applied the same
held drive targets for `H=10` physics steps. Across all ten episodes:

| Quantity | Maximum absolute difference |
| --- | ---: |
| Object pose | 0.0 |
| Object linear velocity | 0.0 |
| Object angular velocity | 0.0 |

PhysX solver warm-start caches are not exposed. The zero difference verifies
this bounded replay contract on the tested states; it is not a claim that all
arbitrary long-horizon PhysX branches are bitwise deterministic.

## Time-aligned trace statistics

Across the ten selected successes:

| Metric | Min | Median | Max |
| --- | ---: | ---: | ---: |
| E2→E5 overlap duration | 4.576 s | 4.736 s | 4.840 s |
| E3→E4 stable-overlap duration | 2.592 s | 2.658 s | 2.844 s |
| E5→E6 receiver-only confirmation | 0.056 s | 0.056 s | 0.056 s |
| Minimum block height | 0.8399999 m | 0.8400000 m | 0.8400000 m |

Per-episode curves are under [`smoke_assets/curves`](smoke_assets/curves), and
the extracted statistics are in
[`smoke_trace_metrics.json`](smoke_assets/smoke_trace_metrics.json).

## Direct answers to the smoke questions

- Real bimanual overlap: **yes**, both actor-ID contacts persist between E2
  and E5, and all ten videos visibly show the overlap.
- Donor/receiver identity: **yes**, donor is left and receiver is right for
  every tested seed, consistent with the initial object-x rule.
- Deterministic snapshot replay: **yes for the bounded E3/H=10 contract**, with
  zero measured pose/twist difference in all ten selected episodes.
- Neutral gripper holds grasp: **drive target and normalized closure are held**;
  the deterministic audit preserves the contact state. The formal LR/L/R/ZERO
  branch rollout is still pending.
- Left/right action dimension: **6+1 per arm, 14 total**.
- Contact actor IDs: **readable** in every selected episode.
- Object pose/twist: **readable at 250 Hz**.
- Single-side gain/delay/friction: **runtime mutation audit passed**.

## Follow-on status

`DONE`: ten-success smoke, E0--E6 detector, manual audit, replay audit, and
mutation capability audit.

After this smoke, six bounded one-seed LR/L/R/ZERO pilots were run. They found
a localized oracle response only after a deliberately strong, diagnostic
compliance intervention; the ordinary profiles did not reliably create a real
object-authority swap. The outcome is therefore
`PILOT_LOCALIZED_SIGNAL_FORMAL_PENDING`, not a formal `SIGNAL_*` decision. See
[`SIGNAL_PILOT_REPORT.md`](SIGNAL_PILOT_REPORT.md).

No ACT training or inference was started. The PAI preflight also failed closed
before `CreateJob` because the shared registry was dirty and its helper hash
disagreed with the active skill contract. See
[`PAI_PREFLIGHT_BLOCK.json`](PAI_PREFLIGHT_BLOCK.json).
