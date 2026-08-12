# R22-P19 LIBERO Phase-1 result

The registered `signal-v1-20260813` audit completed with
`LIBERO_SUBSTRATE_NO_GO`. Seven of nine registered gates passed; two failed:

- responsibility phase AUC over the best-direction arm-action-magnitude
  baseline was `0.0453244715`, below the registered `0.05` margin; and
- push-task gripper gate activation was `47/414 = 0.1135265700`, above the
  registered `0.05` maximum.

ACT training and inference were therefore not launched. No PAI job was
created. This is a registered scientific stage stop, not an infrastructure
failure.

## Evidence boundary

- This is privileged expert/simulator evidence on a single Panda arm.
- The original bimanual Signal GO remains `not_tested`.
- No deployable responsibility model, ACT result, pi0.5 result, world model,
  VLA generality, closed-loop learned-policy result, or real-robot result was
  produced.
- `accepted=false`.

## Persisted evidence

- dev14 output:
  `/mnt/cpfs/zbl-cpfs-new/USERS/leon/logs/r22p19_libero_phase1/signal-v1-20260813`
- `metrics.json` SHA256:
  `693da04b14d6bbebe757ad769a7aef6fcaf7a13336d0f94dab1a93b223864dff`
- `decision.json` SHA256:
  `06b90e08ede5645dfd88fd2fd0d195a5f933b0e6f94b7f94179e8fb36f696507`
- `EVALUATION_COMPLETE.json` SHA256:
  `3b33c5de8ae1b522a9c323ea47420e802cdbed3538e2e8d7936c28fd8787f3ad`
- Feishu Wiki report:
  `https://icnbwz7kd1ui.feishu.cn/wiki/XRB7wg9pKin6rvk9WsYciEf6npe`

The compact machine-readable result is in
`results/signal-v1-20260813/summary.json`. Large traces and branch records
remain on CPFS and are intentionally not committed to Git.
