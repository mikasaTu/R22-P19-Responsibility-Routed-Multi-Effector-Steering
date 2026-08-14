# R22-P19 Responsibility-Routed Multi-Effector Steering

This repository preserves both the Phase-1 LIBERO action-subspace proxy and
the continuing Stage-2 RoboTwin dual-arm validation.

## Current result

The current Stage-2C decision is
**`RESPONSIBILITY_MECHANISM_NOT_SUPPORTED`** with `accepted=false`.

- Fresh-prefix independent-process replay reduced every exact-null median,
  P95, and maximum floor to zero; the Stage-2B floor was caused by restoring
  explicit state without restoring hidden PhysX warm-start history.
- Natural/soft-hidden responsibility was unstable: expected hidden-authority
  accuracy was 0.3167 (95% CI [0.2417, 0.4000]) while the reversed contrast
  was 0.6833.
- The replacement nullspace operator was numerically effectful (local median
  correction ratio 0.1733) and conserved predicted total effect, but correct,
  swapped, and conservation-only targets produced no causal responsibility
  movement.
- Despite the negative gates, the user-requested full diagnostic matrix was
  completed: 448/448 fresh-process cells across eight held-out episodes, four
  conditions, and fourteen methods. Correct responsibility beat swapped and
  shuffled in 0/3 stresses; full routing beat conservation-only in 0/3; C13
  improved 0/3 stresses by the preregistered rule.
- ACT remains blocked. No PAI job, learned estimator, VLA training, deployable
  closed loop, or real-robot result was produced.

Detailed reports:

- [`STEP4_EXPERIMENT_REPORT.md`](stage2_robotwin/stage2c/reports/STEP4_EXPERIMENT_REPORT.md)
- [`CLOSED_LOOP_REPORT.md`](stage2_robotwin/stage2c/reports/CLOSED_LOOP_REPORT.md)
- [`MECHANISM_REVERSE_EXPLANATION.md`](stage2_robotwin/stage2c/reports/MECHANISM_REVERSE_EXPLANATION.md)
- [`CURRENT_STAGE2C_DECISION.json`](stage2_robotwin/stage2c/reports/CURRENT_STAGE2C_DECISION.json)

## Evidence boundary

Stage 2C is a bounded eight-held-out-episode `handover_block` simulator-oracle
mechanism study. Its three frozen stresses failed the preregistered eligibility
gate and all methods remained at a task-success ceiling, so the completed
matrix is diagnostic falsification rather than a qualified failure-space
performance benchmark. The operator uses privileged simulator branches and
object/contact state; the result establishes neither policy compatibility nor
deployability.

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
- Stage-2C test and artifact receipts:
  [`STAGE2C_TEST_RESULTS.md`](stage2_robotwin/stage2c/reports/STAGE2C_TEST_RESULTS.md)
- Stage-2 test and artifact receipts:
  [`STAGE2_TEST_RESULTS.md`](stage2_robotwin/reports/STAGE2_TEST_RESULTS.md)
- Historical Phase-1 report:
  [`docs/EXPERIMENT_REPORT.md`](docs/EXPERIMENT_REPORT.md)

Datasets, external RoboTwin assets, model weights, environments, credentials,
and unrelated worktrees are not committed.
