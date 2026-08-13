# R22-P19 Responsibility-Routed Multi-Effector Steering

This repository preserves both the Phase-1 LIBERO action-subspace proxy and
the continuing Stage-2 RoboTwin dual-arm validation.

## Current result

The current Stage-2 decision is
**`PILOT_LOCALIZED_SIGNAL_FORMAL_PENDING`** with `accepted=false`.

- Ten selected `handover_block` expert episodes passed the E0--E6 event,
  visual, contact, and deterministic snapshot audits.
- Real LR/L/R/ZERO branching runs at H=5 and H=10.
- Ordinary expert-action and direction/null profiles did not reliably create
  an object-authority swap.
- A deliberately strong diagnostic (`0.05` compliance on the non-dominant
  arm) created 21 valid paired comparisons across 12 transition steps in one
  episode; oracle direction was correct on all 21.
- This positive result is localized, one-seed, simulator privileged, and
  intervention-confounded. It is not a formal `SIGNAL_*` classification.
- No operator, ACT training/inference, PAI job, learned closed loop, or real
  robot result exists yet.

The detailed result is in
[`stage2_robotwin/reports/SIGNAL_PILOT_REPORT.md`](stage2_robotwin/reports/SIGNAL_PILOT_REPORT.md).

## Evidence boundary

The formal Stage 2A contract calls for 30 successful plus 20 perturbed
`handover_block` episodes, as well as `lift_pot`, `pick_dual_bottles`, and
`handover_mic` controls. Current signal progress is one episode and no control
task. The stored oracle uses simulator snapshots and privileged contact/object
state; it is not deployable.

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

Stage-2 reproduction commands and the frozen external-runtime contract are in
[`stage2_robotwin/README.md`](stage2_robotwin/README.md).

## Reports

- Stage-2 smoke:
  [`SMOKE_REPORT.md`](stage2_robotwin/reports/SMOKE_REPORT.md)
- Stage-2 signal pilot:
  [`SIGNAL_PILOT_REPORT.md`](stage2_robotwin/reports/SIGNAL_PILOT_REPORT.md)
- Current machine decision:
  [`CURRENT_DECISION.json`](stage2_robotwin/reports/CURRENT_DECISION.json)
- Stage-2 test and artifact receipts:
  [`STAGE2_TEST_RESULTS.md`](stage2_robotwin/reports/STAGE2_TEST_RESULTS.md)
- Historical Phase-1 report:
  [`docs/EXPERIMENT_REPORT.md`](docs/EXPERIMENT_REPORT.md)

Datasets, external RoboTwin assets, model weights, environments, credentials,
and unrelated worktrees are not committed.
