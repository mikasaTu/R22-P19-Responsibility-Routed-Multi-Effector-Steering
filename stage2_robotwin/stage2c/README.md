# R22-P19 Stage 2C

This subtree evaluates natural responsibility continuity, an effectful
effect-nullspace operator, and fresh-prefix closed-loop controls on RoboTwin
`handover_block`.  It is a simulator-only privileged-oracle study:
`accepted=false`, no ACT or responsibility estimator is trained, and no PAI
job is created.

## Frozen runtime

- RoboTwin: `266f3aadf505a4f7fe9af0faa41a20f5f47cd123`
- XPolicyLab gitlink: `c37109c500be67d0dea6b36bf7337bbd26e763cd`
- Python: `/mnt/cpfs/zbl-cpfs-new/USERS/leon/deps/r22p19_stage2/venv/bin/python`
- Formal config: `configs/stage2c_formal_eta0p25.yaml`
- One fresh process per seed x condition x method x replicate
- Episode is the only inference unit; branch points are not independent

The raw expert tapes, per-cell traces, runtime logs, environments, datasets,
weights, and credentials are excluded from Git.  Compact decisions, tape
hashes, reports, configs, tests, and publication audits are retained.

## Entry point

On dev14, set the repository and external runtime roots and call the shared
launcher:

```bash
repo=/mnt/cpfs/zbl-cpfs-new/USERS/leon/code/R22-P19-Responsibility-Routed-Multi-Effector-Steering
robotwin=/mnt/cpfs/zbl-cpfs-new/USERS/leon/deps/r22p19_stage2/RoboTwin
venv=/mnt/cpfs/zbl-cpfs-new/USERS/leon/deps/r22p19_stage2/venv
config=$repo/stage2_robotwin/stage2c/configs/stage2c_formal_eta0p25.yaml

cd "$repo"
R22P19_STAGE2C_CONFIG="$config" \
  ./stage2_robotwin/stage2c/scripts/run_stage2c_dev14.sh
```

The launcher exposes `capture-tapes`, `replay-noise`, `natural`, `soft-audit`,
`local-gate`, `stress-calibration`, `closed-loop`, and `analyze`.  Every
physics command requires explicit `--tape-root` and `--output` paths; consult
the corresponding module's `--help` before rerunning.  Do not overwrite the
formal CPFS roots recorded in `results/PROVENANCE.json`.

## Tests

```bash
cd /mnt/cpfs/zbl-cpfs-new/USERS/leon/code/R22-P19-Responsibility-Routed-Multi-Effector-Steering
PYTHONPATH=. \
  /mnt/cpfs/zbl-cpfs-new/USERS/leon/deps/r22p19_stage2/venv/bin/python \
  -m pytest -q stage2_robotwin/tests stage2_robotwin/stage2b/tests \
  stage2_robotwin/stage2c/tests
```

The final scientific decision is in
`reports/CURRENT_STAGE2C_DECISION.json`; mechanism claims must be read with
`reports/MECHANISM_REVERSE_EXPLANATION.md` and the negative gate lineage.
