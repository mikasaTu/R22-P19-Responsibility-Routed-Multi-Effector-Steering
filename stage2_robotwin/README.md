# Stage 2: RoboTwin bimanual oracle validation

This subtree continues R22-P19 on a real dual-arm `handover_block` task. The
current outcome is `PILOT_LOCALIZED_SIGNAL_FORMAL_PENDING`; see
[`reports/SIGNAL_PILOT_REPORT.md`](reports/SIGNAL_PILOT_REPORT.md).
Final code and artifact checks are recorded in
[`reports/STAGE2_TEST_RESULTS.md`](reports/STAGE2_TEST_RESULTS.md).

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
