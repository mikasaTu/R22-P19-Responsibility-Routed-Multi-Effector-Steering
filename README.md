# R22-P19 Responsibility-Routed Multi-Effector Steering

This repository is the complete, evidence-preserving publication of the
R22-P19 Phase-1 LIBERO preliminary validation performed on 2026-08-13.

## Result

The preregistered decision is **`LIBERO_SUBSTRATE_NO_GO`**. Seven of nine
registered gates passed. Two failed:

1. phase AUC improvement over the best-direction arm-action-magnitude
   baseline was `0.0453244715`, below the registered `0.05`; and
2. gate-off gripper activation on the push control was
   `47/414 = 0.1135265700`, above the registered `0.05` maximum.

ACT training and inference were therefore skipped. No PAI job was created.
This is a scientific stage stop, not an infrastructure failure.

## Evidence boundary

Standard LIBERO uses one Panda arm. The experiment tests responsibility
between action subspaces (arm pose versus gripper) and a controlled x/y gain
swap. It does **not** test the original left-to-right bimanual responsibility
transfer.

- expert/simulator privileged evidence: present
- learned ACT policy evidence: absent, skipped by the signal gate
- original bimanual Signal GO: `not_tested`
- deployable responsibility estimator: absent
- pi0.5 or world model: not used
- VLA generality or real-robot evidence: absent
- `accepted=false`

## Repository layout

```text
configs/                  Frozen signal configuration
docs/                     Experiment report, provenance, and original request
evidence/                 Every persisted smoke and formal signal artifact
r22p19_libero/            Counterfactual simulator audit implementation
results/                  Compact machine-readable result
scripts/                  dev14 smoke and full signal entrypoints
tests/                    Unit tests and persisted dev14 test receipt
preregistration.yaml      Registered gates and pre-method smoke amendment
RESULT.md                 Concise result handoff
SHA256SUMS                Integrity manifest for all tracked publication files
```

The `evidence/` directory includes all six run directories from the work:
`smoke-v1` through `smoke-v5` and `signal-v1`. Failed early smoke attempts are
retained because they document the EGL, robosuite gripper-state, event-order,
and hidden-controller-state issues found before method metrics were produced.

## Reproduce on dev14

The frozen runtime is:

- LIBERO commit: `8f1084e3132a39270c3a13ebe37270a43ece2a01`
- Python: `/mnt/cpfs/zbl-cpfs-new/USERS/leon/envs/libero-original/bin/python`
- dataset root: `/mnt/cpfs/zbl-cpfs-new/dataset/leon/libero`
- source runtime UID:GID: `2254:2254`

Run tests:

```bash
PYTHONPATH=. /mnt/cpfs/zbl-cpfs-new/USERS/leon/envs/libero-original/bin/python \
  -m pytest -q tests
```

Run the bounded smoke:

```bash
R22P19_CODE_DIR="$PWD" scripts/run_dev14_smoke.sh
```

Run the full oracle audit with a new output directory and run ID:

```bash
R22P19_CODE_DIR="$PWD" \
R22P19_RUN_ID="signal-reproduction-$(date -u +%Y%m%dT%H%M%SZ)" \
scripts/run_signal_audit.sh
```

Do not launch ACT unless every registered signal gate passes in a fresh run.

## Reports

- Repository report: [`docs/EXPERIMENT_REPORT.md`](docs/EXPERIMENT_REPORT.md)
- Feishu child document:
  <https://icnbwz7kd1ui.feishu.cn/wiki/XRB7wg9pKin6rvk9WsYciEf6npe>
- Compact result: [`results/signal-v1-20260813/summary.json`](results/signal-v1-20260813/summary.json)

No datasets, model weights, credentials, or unrelated steering-repository
history are included.
