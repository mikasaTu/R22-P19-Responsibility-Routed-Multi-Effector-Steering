# Oracle signal evidence lineage

These directories preserve six bounded, one-seed RoboTwin
`handover_block` pilots. They are a debugging and preliminary mechanism audit,
not the preregistered formal Stage 2A sample.

- `pilot-v1`: initial branch implementation and invalid drive-target neutral.
- `pilot-v2-neutral-qpos`: corrected measured-qpos neutral.
- `pilot-v3-horizon-sensitivity`: H=5/10/25/50 diagnostic.
- `pilot-v4-direction-null`: Jacobian-validated geometric direction profiles.
- `pilot-v5-compliance-assisted`: sparse strong-compliance diagnostic.
- `pilot-v6-dense-transition`: final bounded dense transition-window pilot.

Each run retains its trace, video, JSONL branch outcomes, runtime log, source
manifest, plot, and machine metrics. The current scientific interpretation is
in [`../../reports/SIGNAL_PILOT_REPORT.md`](../../reports/SIGNAL_PILOT_REPORT.md).
