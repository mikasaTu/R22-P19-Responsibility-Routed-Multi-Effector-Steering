# Code-first mechanism reverse explanation

This note explains the observed positive signal replication and weak operator
result from implementation and runtime evidence. It does not propose a new
research idea.

## 1. Why the contact-aware probe changed the signal result

### Code path

`TaskFrameFollower.target()` measures object displacement from the snapshot,
projects it onto `e_parallel`, and moves only the follower's parallel setpoint
by `(1-gamma)` of that displacement. Its rotation target and all orthogonal
support targets remain the snapshot targets. `ContactAwareAuthorityProbe` then
applies a 4 mm direction command to exactly one designated driver while holding
both gripper drive targets.

### Consequence

The original direction/null intervention asked one hand to drive while the
other hand remained a rigid positional constraint. The object therefore could
not realize the intended single-arm task-direction motion. The new follower
removes that constraint on one axis without opening the grasp, so the active
driver becomes mechanically observable. This accounts for the transition from
0 ordinary valid swaps to held-out valid-pair rates of 0.8529--0.8824.

### Boundary revealed by the same code

Each LEFT/RIGHT profile has only one active driver. The profile's `LR` and the
active singleton therefore coincide, while the other singleton is neutral.
That construction predicts and explains:

- orientation accuracy of 1.0;
- responsibility margin of 2.0;
- essentially zero `rho_joint`;
- identical summaries for every tested gamma.

The positive result is consequently evidence that a matched intervention can
make counterfactual direction identifiable. It is not evidence that natural
unmodified handover responsibility is already identifiable or that the probe
recovers interaction synergy.

## 2. Why the conserved operator barely changes the action

`OneDimensionalEffectConservingTransfer` solves two scalar action variables
under the equality `b_L*a_L + b_R*a_R = d_base`, a 2 mm trust region, and a
quadratic pull toward the base action. The Hessian diagonal is
`b_i^2 + lambda`.

Runtime medians show `b_i^2 = 1.863e-4` for B7 while `lambda=0.05`, giving
`lambda / median(b_i^2) = 268.36`. The regularizer therefore dominates the
responsibility target. Exact conservation is achieved mainly by returning the
base action:

- median B11 correction: `5.42e-20 m`;
- P95 B11 correction: `1.95e-6 m`;
- median base-action magnitude: `1.042e-3 m`;
- corrections above 1 micrometre: 11.73%;
- trust-region clips: 0.

This is why the solver can be 100% feasible with `~1e-21 m` conservation error
yet provide no stable closed-loop improvement. Algebraic correctness and
control efficacy are different claims.

## 3. Why two-way and three-way look similar

`responsibility_weights()` bypasses transfer only when
`abs(rho_joint) > 0.2`. B7 selected `JOINT_SUPPORT` on only 75 of 23,124 logged
steps (0.324%); B6 and B7 therefore execute the same dominant-arm mode almost
everywhere. A three-way benefit is not estimable from this occupancy.

## 4. Why release-guard gains are weak

The release guard observes 5,200 open requests per method, but B11 blocks only
25 (0.481%); release-guard-only B10 blocks 75. All 240 runs still succeed with
no drop or premature release. The guard has too little activation and no
failure headroom to create an identifiable task-level effect.

## 5. Why small metric changes alternate sign

B0 and the exact-action null B9 execute identical arm/gripper targets and the
same oracle estimator schedule. Nevertheless their maximum absolute
episode-level differences are:

- angular velocity: `0.6235`;
- linear jerk: `2.3277`;
- contact-masked slip: `0.000610 m`.

The in-memory snapshot restores exposed SAPIEN state but not the PhysX solver
warm-start cache. Method order was rotated, yet only five episodes are
available. The B0/B9 differences therefore measure a replay/hidden-state noise
floor. Most B11 effects and all sign-changing confidence intervals sit inside
that floor, so apparent improvements or degradations cannot be attributed to
routing.

## 6. Why the stress pilot was under-informative

The three frozen perturbations left B0 success at 1.0 in every episode. All
methods also had 1.0 success and zero drops. The preregistered 40%--80% base
success target was missed. Disturbance metrics remain usable, but task metrics
are ceilinged and the pilot cannot show rescue of a failure regime.

## 7. Mechanism conclusion

The signal improvement is explained by removal of the follower's parallel
kinematic opposition. The operator weakness is explained jointly by a
regularization-dominated near-null action map, sparse joint/guard activation,
insufficient stress, and replay noise larger than the intervention. No new
idea, learned estimator, VLA claim, or deployable mechanism is inferred.
