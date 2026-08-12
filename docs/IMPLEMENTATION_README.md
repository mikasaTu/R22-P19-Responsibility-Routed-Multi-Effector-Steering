# R22-P19 LIBERO Phase-1

This directory contains the user-authorized preliminary validation of
`R22-P19: Responsibility-Routed Multi-Effector Steering` on LIBERO.

## Evidence boundary

Standard LIBERO uses one Panda arm. It cannot test left-to-right bimanual
handoff or establish deployable multi-effector responsibility. This pilot
instead tests two narrower prerequisites:

1. whether simulator counterfactual branches recover phase-dependent causal
   responsibility between the arm-pose and gripper actuator groups; and
2. whether the recovered attribution follows a controlled x/y actuator-gain
   swap rather than a fixed coordinate identity.

The primary task is `libero_goal/put_the_bowl_on_the_plate`; the gate-off
control is `libero_goal/push_the_plate_to_the_front_of_the_stove`. CPU tests
and the bounded dev14 smoke validate only implementation and replay
determinism. They are not method-performance evidence.

ACT training is conditional on the LIBERO substrate signal gate. Even a
positive substrate gate does not satisfy the original bimanual Signal GO
gate. Reports must keep `accepted=false`.

## Runtime contract

- LIBERO source: official commit `8f1084e3132a39270c3a13ebe37270a43ece2a01`
- ACT source: Hugging Face LeRobot commit
  `0cf864870cf29f4738d3ade893e6fd13fbd7cdb5`
- dev14 Python for simulator audit:
  `/mnt/cpfs/zbl-cpfs-new/USERS/leon/envs/libero-original/bin/python`
- persistent outputs:
  `/mnt/cpfs/zbl-cpfs-new/USERS/leon/logs/r22p19_libero_phase1/<run_id>`

Run the bounded smoke with `scripts/run_dev14_smoke.sh`. Formal signal audit
and any later ACT workload use separate commands and persisted run IDs.

The full oracle audit is `scripts/run_signal_audit.sh`. It writes source and
dataset hashes, deterministic replay checks, event traces, every compact
counterfactual branch, registered metrics, and an atomic decision marker.
ACT is not launched when that marker is `LIBERO_SUBSTRATE_NO_GO`.

LIBERO HDF5 flat states do not contain Python-side OSC buffers or
`PandaGripper.current_action`. The audit therefore persists one common
hidden-state intervention for every branch: OSC is anchored to the restored
robot state and the gripper actuator target holds the restored finger qpos.
Exact next-recorded-state replay remains a diagnostic; exact repeated-branch
identity is the determinism gate.
