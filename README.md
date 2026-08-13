# R22-P19 Responsibility-Routed Multi-Effector Steering

This repository preserves both the Phase-1 LIBERO action-subspace proxy and
the continuing Stage-2 RoboTwin dual-arm validation.

## Current result

The current Stage-2B decision is **`SIGNAL_VALID_OPERATOR_WEAK`** with
`accepted=false`.

- A contact-aware follower intervention was calibrated on seeds `0,1` and
  frozen before evaluation on held-out seeds `2,3,5,6,7`.
- At non-extreme `gamma=0.6`, mean episode valid-pair rate was 0.8706
  (95% CI [0.8588, 0.8824]); oracle orientation accuracy was 1.0
  (95% CI [1.0, 1.0]); shuffled orientation was 0.5001.
- The 1-D simulator-oracle operator pilot completed all 240 paired replays
  (5 episodes x 4 conditions x 12 methods), all without drop.
- Exact effect conservation passed, but the operator was numerically near-null
  and did not improve all primary disturbance metrics consistently over the
  base or heuristic controls. Specificity was not demonstrated.
- ACT was skipped by the oracle-operator gate. No PAI job, learned estimator,
  VLA training, deployable closed loop, or real-robot result was produced.

Detailed reports:

- [`SIGNAL_REPLICATION_REPORT.md`](stage2_robotwin/stage2b/reports/SIGNAL_REPLICATION_REPORT.md)
- [`ORACLE_OPERATOR_REPORT.md`](stage2_robotwin/stage2b/reports/ORACLE_OPERATOR_REPORT.md)
- [`MECHANISM_REVERSE_EXPLANATION.md`](stage2_robotwin/stage2b/reports/MECHANISM_REVERSE_EXPLANATION.md)

## Evidence boundary

Stage 2B is a bounded five-held-out-episode `handover_block` mechanism pilot.
The contact-aware probe intentionally constructs authority on the horizontal
task axis, and the closed-loop operator uses privileged simulator branches and
object/contact state. The result neither completes the larger Stage 2A task
suite nor establishes policy compatibility or deployability.

The historical Phase-1 `LIBERO_SUBSTRATE_NO_GO` remains valid for its
single-arm arm-pose-versus-gripper proxy, but it neither proves nor disproves
the original bimanual proposition.

## Repository layout

```text
stage2_robotwin/          RoboTwin code, configs, tests, reports, traces, videos
r22p19_libero/            Historical Phase-1 LIBERO implementation
evidence/                 Historical Phase-1 raw evidence
docs/                     Phase-1 report and provenance
results/                  Phase-1 compact result
SHA256SUMS                Integrity manifest
PUBLICATION_AUDIT.json    Publication and verification audit
```

Stage-2/2B reproduction commands and the frozen external-runtime contract are in
[`stage2_robotwin/README.md`](stage2_robotwin/README.md).

## Reports

- Stage-2 smoke:
  [`SMOKE_REPORT.md`](stage2_robotwin/reports/SMOKE_REPORT.md)
- Stage-2 signal pilot:
  [`SIGNAL_PILOT_REPORT.md`](stage2_robotwin/reports/SIGNAL_PILOT_REPORT.md)
- Current machine decision:
  [`CURRENT_DECISION.json`](stage2_robotwin/reports/CURRENT_DECISION.json)
- Stage-2B machine decision:
  [`CURRENT_STAGE2B_DECISION.json`](stage2_robotwin/stage2b/reports/CURRENT_STAGE2B_DECISION.json)
- Stage-2B test and artifact receipts:
  [`STAGE2B_TEST_RESULTS.md`](stage2_robotwin/stage2b/reports/STAGE2B_TEST_RESULTS.md)
- Stage-2 test and artifact receipts:
  [`STAGE2_TEST_RESULTS.md`](stage2_robotwin/reports/STAGE2_TEST_RESULTS.md)
- Historical Phase-1 report:
  [`docs/EXPERIMENT_REPORT.md`](docs/EXPERIMENT_REPORT.md)

Datasets, external RoboTwin assets, model weights, environments, credentials,
and unrelated worktrees are not committed.
