# R22-P19 current result

Current status: `PILOT_LOCALIZED_SIGNAL_FORMAL_PENDING`

Formal Stage-2A signal label: not assigned

Acceptance: `accepted=false`

The Stage-2 RoboTwin substrate is operational: ten selected dual-arm
`handover_block` episodes pass E0--E6 and snapshot replay, and the
simulator-privileged LR/L/R/ZERO oracle branch pipeline runs end to end.

In the final bounded one-seed pilot, 46 states were evaluated at H=5 and
H=10. Ordinary direction/null produced `0/92` valid object-authority swaps.
A diagnostic `0.05` non-dominant-arm compliance profile produced `21/92`
valid pairs across 12 unique transition steps; oracle direction accuracy on
those independently validated pairs was `21/21`.

This is localized preliminary mechanism evidence. It does not clear the
formal 30+20 episode contract, does not include control tasks, and does not
establish operator benefit or deployability. ACT/PAI training and inference
were not started, and no PAI job was created.

See:

- `stage2_robotwin/reports/SIGNAL_PILOT_REPORT.md`
- `stage2_robotwin/reports/SMOKE_REPORT.md`
- `stage2_robotwin/reports/CURRENT_DECISION.json`
- `stage2_robotwin/results/oracle_signal/pilot-v6-dense-transition/`

The earlier single-arm LIBERO result remains
`LIBERO_SUBSTRATE_NO_GO` for that proxy only; it is retained under `docs/`,
`evidence/`, and `results/`.
