# R22-P19 Stage 2B-I signal replication

Date: 2026-08-14

Task: RoboTwin `handover_block`

Decision: **`MULTISEED_SIGNAL_SUPPORTED`**

Acceptance: `accepted=false`

## What was tested

The Stage 2A direction/null probe had no valid ordinary authority swaps because
the other rigidly grasping arm constrained object motion. Stage 2B-I therefore
used the preregistered controller fallback: a contact-aware task-frame follower.
The driver received a 4 mm command along the horizontal handover direction; the
follower tracked only that direction while retaining its snapshot support and
rotation targets. Both gripper drive targets remained unchanged.

Native Cartesian anisotropic stiffness was not available in this RoboTwin
joint-drive controller. The implementation consequently does **not** claim to
be physical stiffness control. `gamma` is the retained parallel position-error
ratio of the follower target.

Calibration and held-out evaluation were separated:

- calibration seeds: `0, 1`;
- held-out seeds: `2, 3, 5, 6, 7`;
- frozen primary `gamma=0.6` (largest eligible non-extreme value);
- diagnostic `gamma=0.05` was not required for the positive result;
- window: `[E4-250, min(E5, E4+150)]`, stride 25 physics steps;
- horizons: `H=5,10`;
- each state/profile/horizon ran `LR/L/R/ZERO` from the same snapshot;
- statistical unit: episode, with 10,000-repetition episode bootstrap.

The frozen configuration SHA-256 is
`30e80b4811c17ceafd9c928cd583ac8505ebb764a8cc8f19b57db7917e08a3b1`.

## Held-out results

At the frozen `gamma=0.6`, every held-out episode had valid authority pairs:

| Seed | Valid pairs | Candidate pairs | Valid-pair rate | Oracle orientation accuracy |
| ---: | ---: | ---: | ---: | ---: |
| 2 | 30 | 34 | 0.8824 | 1.0000 |
| 3 | 29 | 34 | 0.8529 | 1.0000 |
| 5 | 29 | 34 | 0.8529 | 1.0000 |
| 6 | 30 | 34 | 0.8824 | 1.0000 |
| 7 | 30 | 34 | 0.8824 | 1.0000 |

- Mean episode valid-pair rate: **0.8706**, bootstrap 95% CI
  **[0.8588, 0.8824]**.
- Mean episode oracle orientation accuracy on valid pairs: **1.0000**, 95% CI
  **[1.0000, 1.0000]**.
- Shuffled episode-profile orientation control: **0.5001**.
- Median episode responsibility margin: **2.0** for every held-out seed.
- Median `|rho_joint|` was numerically zero; frozen-threshold joint-mode
  occupancy was **0.0**.
- `gamma=0.6,0.4,0.2,0.05` produced the same held-out validity summary, so the
  result does not rely on the extreme diagnostic setting.

## Mechanism interpretation

The positive change from Stage 2A is explained by code and trace behavior. The
follower no longer fixes its end-effector along `e_parallel`; it tracks a
fraction `(1-gamma)` of object displacement on that one axis while preserving
the other targets. This removes the rigid kinematic opposition that previously
prevented a driver command from becoming object motion.

The same construction also bounds the claim. Each profile contains only one
active driver, so `LR` equals the active singleton and the opposite singleton
is neutral by design. This explains the saturated margin, gamma insensitivity,
and essentially zero `rho_joint`. The experiment demonstrates that the
counterfactual orientation is repeatable under a valid contact-aware authority
intervention; it does **not** demonstrate a deployable estimator, natural
unperturbed responsibility, or three-way synergy.

## Decision and boundary

The preregistered held-out rule is met, so the Stage 2B-I classification is
`MULTISEED_SIGNAL_SUPPORTED`. `accepted` remains false. This is a
simulator-privileged oracle result on five successful `handover_block` episodes
and is not a VLA, learned policy, broad task-suite, real-robot, or paper-level
validation.

Primary machine-readable evidence:

- `results/signal_replication/calibration-v2/frozen_signal_config.json`
- `results/signal_replication/heldout-v1/signal_replication_metrics.json`
- `results/signal_replication/heldout-v1/run_summary.json`
- `reports/SIGNAL_REPLICATION_DECISION.json`
