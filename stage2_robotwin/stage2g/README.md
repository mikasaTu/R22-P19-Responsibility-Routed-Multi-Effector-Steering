# Step9 reproduction and evidence
Read reports/STEP9_PREFLIGHT.md first. This is a completed Delivery 1 preflight,
not an accepted authority probe or a completed Stage I/II experiment.
Smoke source is commit 2cddb2b; final ownership/binding checks and the locked
control were added afterward and have unit-test evidence only.

## Verify
From the repository root, using the pinned dev14 Python environment:
    python -m pytest -q stage2_robotwin/stage2g/tests
    python -m pytest -q stage2_robotwin
    python -m stage2_robotwin.stage2g.scripts.analyze_preflight --root stage2_robotwin/stage2g/results/preflight --output /absolute/new/path/decision.json

The analyzer verifies original trace SHA256 and complete effect hashes. If the
original CPFS trace path does not exist, it uses the co-located archived trace.
Frozen nominal and six pair tapes are under results/preflight/frozen-seed0.
The original seed 0/1 source tapes and sidecars are under preregistration/source-tapes.
The input/runtime revisions and patches are recorded in INPUT_PROVENANCE.json
and every smoke source_identity. The external RoboTwin runtime/assets and pinned
dependencies are required for simulation; repository unit tests do not replace them.
For fresh simulation use scripts/run_probe_cell.py --help, supply absolute paths
for all inputs/outputs (RoboTwin changes the working directory), and a new output
directory. No existing result may be overwritten.

## Integrity and scope
Run sha256sum -c SHA256SUMS from the repository root for the published inventory,
or from this stage2g directory for its own relative inventory.
Original frozen sidecars are preserved byte-for-byte. MAPPING_AUDIT_CORRECTION.json
corrects only an unsigned/signed diagnostic error; the stored command arrays are
unchanged. Five archived cells all use seed 0. Seed 1 was only hash-verified.
Stage I has 24 enumerated cells, Stage II 48 conditional cells, and neither has
been executed. The mandatory user confirmation checkpoint remains in force.
