# Stage 2: RoboTwin bimanual oracle validation

This subtree continues R22-P19 on the dual-arm `handover_block` simulator task.
The current Stage 2C outcome is `RESPONSIBILITY_MECHANISM_NOT_SUPPORTED`; see
the [`Step4 report`](stage2c/reports/STEP4_EXPERIMENT_REPORT.md),
[`mechanism explanation`](stage2c/reports/MECHANISM_REVERSE_EXPLANATION.md), and
[`machine decision`](stage2c/reports/CURRENT_STAGE2C_DECISION.json). Historical
Stage 2A/2B evidence and negative lineage remain unchanged.

## Reproduce the bounded runs on dev14

External runtime contract:

- RoboTwin: `266f3aadf505a4f7fe9af0faa41a20f5f47cd123`
- XPolicyLab gitlink: `c37109c500be67d0dea6b36bf7337bbd26e763cd`
- Python: `/mnt/cpfs/zbl-cpfs-new/USERS/leon/deps/r22p19_stage2/venv/bin/python`
- planner: explicit `mplib_screw`
- renderer: one free NVIDIA A800 GPU selected by `CUDA_VISIBLE_DEVICES`

Run unit tests:

```bash
PYTHONPATH=. /mnt/cpfs/zbl-cpfs-new/USERS/leon/deps/r22p19_stage2/venv/bin/python \
  -m pytest -q stage2_robotwin/tests
```

Run the ten-episode smoke:

```bash
CUDA_VISIBLE_DEVICES=3 stage2_robotwin/scripts/run_dev14_smoke.sh
```

Run the bounded signal pilot:

```bash
CUDA_VISIBLE_DEVICES=3 \
R22P19_BRANCH_PROFILE_MODE=direction_diagnostic \
R22P19_BRANCH_BASE_STRIDE=25 \
R22P19_BRANCH_SWAP_STRIDE=25 \
R22P19_SIGNAL_RUN_ID=reproduction \
stage2_robotwin/scripts/run_signal_pilot.sh
```

The default signal runner is deliberately a one-episode pilot. Do not call it
a formal Stage 2A audit without meeting the episode, perturbation, and control
task contract in `configs/signal_audit_handover_block.yaml`.

## Reproduce Stage 2B analyses

The retained simulator runs are already complete. Recompute their metrics
without rerunning physics:

```bash
PYTHONPATH=. /mnt/cpfs/zbl-cpfs-new/USERS/leon/deps/r22p19_stage2/venv/bin/python \
  -m stage2_robotwin.stage2b.scripts.analyze_stage2b \
  --mode evaluate \
  --inputs stage2_robotwin/stage2b/results/signal_replication/heldout-v1/branches/*.jsonl \
  --config stage2_robotwin/stage2b/configs/contact_aware_signal.yaml \
  --run-summary stage2_robotwin/stage2b/results/signal_replication/heldout-v1/run_summary.json \
  --frozen-config stage2_robotwin/stage2b/results/signal_replication/calibration-v2/frozen_signal_config.json \
  --output /tmp/r22p19_signal_metrics.json \
  --plot /tmp/r22p19_signal_curve.png

PYTHONPATH=. /mnt/cpfs/zbl-cpfs-new/USERS/leon/deps/r22p19_stage2/venv/bin/python \
  -m stage2_robotwin.stage2b.scripts.analyze_operator_pilot \
  --input stage2_robotwin/stage2b/results/oracle_operator/pilot-v3-contact-slip/pilot_results.json \
  --output /tmp/r22p19_operator_metrics.json \
  --plot /tmp/r22p19_operator_improvement.png
```

The Stage 2B test command is:

```bash
PYTHONPATH=. /mnt/cpfs/zbl-cpfs-new/USERS/leon/deps/r22p19_stage2/venv/bin/python \
  -m pytest -q stage2_robotwin/tests stage2_robotwin/stage2b/tests
```

## Reproduce Stage 2C

Stage 2C uses one fresh process per seed × condition × method, plus a separate
SAPIEN scene for every oracle branch. The exact launcher, frozen CPFS roots,
config hashes, and raw-artifact exclusion contract are documented in
[`stage2c/README.md`](stage2c/README.md). Recompute compact decisions from the
retained formal roots with the `analyze` entry point; do not overwrite those
roots.

The combined Stage 2/2B/2C test command is:

```bash
PYTHONPATH=. /mnt/cpfs/zbl-cpfs-new/USERS/leon/deps/r22p19_stage2/venv/bin/python \
  -m pytest -q stage2_robotwin/tests stage2_robotwin/stage2b/tests \
  stage2_robotwin/stage2c/tests
```

The current gate explicitly blocks ACT and PAI training because correct
responsibility did not beat wrong/shuffled controls or conservation-only.
