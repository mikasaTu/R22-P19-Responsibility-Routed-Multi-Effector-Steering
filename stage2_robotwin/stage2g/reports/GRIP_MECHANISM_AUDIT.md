# K4 grip mechanism and Stage2F wrench trace audit

Date: 2026-09-07

Scope: Stage 2G K4 implementation and a read-only audit of the two published
Stage2F K1 smoke traces. This is an implementation/preflight artifact.
No RoboTwin scene was stepped, no PAI job was created, and no scientific gate
was adjudicated.

## Runtime evidence

The pinned runtime is:

- RoboTwin root: /mnt/cpfs/zbl-cpfs-new/USERS/leon/deps/r22p19_stage2/RoboTwin
- RoboTwin commit: 266f3aadf505a4f7fe9af0faa41a20f5f47cd123
- embodiment config: assets/embodiments/aloha-agilex/config.yml
- repository code under audit: envs/robot/robot.py
- dev14 test interpreter:
  /mnt/cpfs/zbl-cpfs-new/USERS/leon/deps/r22p19_stage2/venv/bin/python

The robot wrapper sets arm and gripper stiffness/damping in
envs/robot/robot.py:212-228. For the gripper it does not pass a finite
force limit. The only gripper control path used by the Stage2 runners is
Robot.set_gripper (robot.py:628-659): it clips a normalized value to [0, 1],
updates left_gripper_val or right_gripper_val, maps it through gripper_scale,
and writes drive target and drive velocity target. The Aloha config declares
gripper stiffness 1000, damping 200, and scale [-0.01, 0.045]
(config.yml:3-16). Its URDF lists effort=100 for the prismatic gripper joints,
but that is URDF metadata; it is not a finite runtime drive-force value
supplied by set_drive_property.

The published Stage2F receipts report the arm drive default
force_limit=3.4028234663852886e+38 (the float32 FLT_MAX value) for every
arm joint. The Stage2F smoke did not persist a separate gripper force-limit
readback, so this report does not claim a direct gripper-object force
measurement. Since the gripper initialization uses the same setter while
omitting force_limit, there is no justified finite force constant to scale.
K4 therefore does not multiply URDF effort or FLT_MAX.

The pinned Aloha URDF names the left gripper links fl_link7/fl_link8 and the
right gripper links fr_link7/fr_link8; they are distinct. The existing contact
classifier can therefore separate the two sides for this pinned embodiment by
link name. It does not persist a per-contact side ID in the Stage2F trace, so a
future generalization should retain side and link identity explicitly.

## K4 implementation

stage2_robotwin/stage2g/intervention/grip_force.py implements
apply(task, soft_arm, gamma) as a context manager.

Because the runtime exposes target opening rather than a finite gripper-force
setter, the implementation is explicitly labelled
implementation=target_opening_fallback and
physical_quantity=normalized_gripper_target_opening. For a soft-arm normalized
command u, the routed target is gamma*u + (1-gamma)*1.0. The endpoint 1.0 is
the wrapper's own normalized open endpoint. gripper_eps=0 is used when
applying that target so the wrapper's default incremental epsilon cannot
silently change the requested target.

The API contract is:

~~~python
with grip_force.apply(task, "left", gamma) as handle:
    command = handle.route_gripper("left", tape_item["left_gripper"])
    task.robot.set_gripper(command[0], "left", command[1])
~~~

The receiver command is returned unchanged. At gamma=1, K4 performs no
setter or restore write, returns the input command object unchanged, and the
receipt marks no_op=true and restoration_required=false. This preserves any
normal episode gripper command issued inside the context; the gamma=1 test
compares final targets, bookkeeping, and setter calls against a no-K4 baseline.
The context manager does not monkey-patch task.robot.set_gripper; every later
soft-arm tape command must pass through route_gripper (or route_item). At
entry, gamma<1 also maps the current soft-arm opening. For gamma<1, the
finally block restores each gripper drive target, drive velocity target, and
normalized *_gripper_val directly, then emits exact-restoration fields in
handle.receipt(). Arm stiffness, damping, force limit, and drive mode are
snapshotted for the receipt and never written.

## Stage2F traceability result

The two trace files are:

- /mnt/cpfs/zbl-cpfs-new/USERS/leon/logs/R22-P19/stage2f/preflight-smoke-v7-final-source/seed_0000__K1__left__gamma_1p0.trace.npz
- /mnt/cpfs/zbl-cpfs-new/USERS/leon/logs/R22-P19/stage2f/preflight-smoke-v7-final-source/seed_0000__K1__left__gamma_0p2.trace.npz

Both contain exactly these arrays, each with shape [1132]:

object_position[1132,3], object_linear_velocity[1132,3],
soft_parallel_impulse[1132], soft_vertical_impulse[1132],
soft_parallel_share[1132], dual_contact[1132], and donor_contact[1132].

The runner does call Stage2E's contact_wrench_by_side, which temporarily
computes a per-side 3-vector impulse and a torque from each contact point
relative to object COM. However, the runner immediately reduces those values
to absolute soft/receiver projections, an absolute-projection share, and
booleans, then writes only the arrays above. It does not persist the left/right
signed impulse vectors, contact positions, per-contact identity, object COM, or
per-side torque.

Consequently the requested w_L, w_R, w_ext=w_L+w_R, and
w_int=(w_L-w_R)/2 cannot be reconstructed from the stored smoke traces. In
particular, an absolute impulse projection cannot reveal the sign or direction
needed to distinguish net motion from equal-and-opposite internal loading, and
torque cannot be recovered without contact positions. The correct audit status
is NOT_RECOVERABLE_FROM_STORED_TRACES; no internal wrench percentage is
reported or inferred.

The scalar changes that are recoverable, but are not a wrench decomposition,
are:

| quantity | gamma=1.0 | gamma=0.2 | delta / ratio |
| --- | ---: | ---: | ---: |
| soft parallel impulse integral | 0.4573193918 | 0.7897836603 | +0.3324642685 / 1.7269848481 |
| soft vertical impulse integral | 0.1780127255 | 0.2746898320 | +0.0966771065 / 1.5430909850 |
| soft parallel impulse-share mean | 0.4553551770 | 0.4505249939 | -0.0048301831 |

These are one smoke episode per condition, so no episode-level 95% CI is
estimable. The higher scalar soft impulse with nearly unchanged scalar share
is compatible with increased internal loading, but that is only a hypothesis
until future cells persist full signed per-side contact wrenches.

## Validation

Executed on dev14 with the required venv:

~~~text
/mnt/cpfs/zbl-cpfs-new/USERS/leon/deps/r22p19_stage2/venv/bin/python -m py_compile \
  stage2_robotwin/stage2g/intervention/grip_force.py stage2_robotwin/stage2g/tests/test_grip_force.py
/mnt/cpfs/zbl-cpfs-new/USERS/leon/deps/r22p19_stage2/venv/bin/python -m pytest -q stage2_robotwin/stage2g/tests/test_grip_force.py
# 7 passed in 0.41s
/mnt/cpfs/zbl-cpfs-new/USERS/leon/deps/r22p19_stage2/venv/bin/python -m pytest -q stage2_robotwin/stage2f/tests stage2_robotwin/stage2g/tests/test_grip_force.py
# 35 passed in 0.96s
~~~

No simulation, scene stepping, PAI submission, Feishu write, or main-branch
push was performed.
