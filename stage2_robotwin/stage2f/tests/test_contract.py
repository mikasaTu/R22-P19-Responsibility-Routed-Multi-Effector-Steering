import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import yaml

from stage2_robotwin.stage2f.active_reference import FrozenActiveReference
from stage2_robotwin.stage2f.scripts.run_authority_knob_cell import sample_steps


def test_frozen_matrix_and_forbidden_seeds():
    path = Path(__file__).parents[1] / "preregistration" / "EXPERIMENT_CONTRACT.yaml"
    contract = yaml.safe_load(path.read_text())
    matrix = contract["matrix"]
    assert len(matrix["seeds"]) * len(matrix["knobs"]) * len(matrix["soft_arms"]) * len(matrix["gammas"]) * matrix["repeats"] == 144
    assert matrix["total_cells"] == 154
    assert contract["seed_contract"]["heldout_forbidden"] == [2, 3, 5, 6, 7, 8, 9, 10]
    assert contract["accepted"] is False and contract["pai_job_created"] is False


def test_current_calibration_windows_have_17_states():
    seed0 = sample_steps({"E3": 3425, "E4": 4083, "E5": 4556})
    seed1 = sample_steps({"E3": 2752, "E4": 3400, "E5": 3882})
    assert len(seed0) == len(seed1) == 17
    assert (seed0[0], seed0[-1]) == (3833, 4233)
    assert (seed1[0], seed1[-1]) == (3150, 3550)


def test_active_reference_complete_lineage_validation(tmp_path):
    source = tmp_path / "source.npz"
    source.write_bytes(b"source-tape")
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    active = tmp_path / "active.npz"
    payload = {"steps": np.arange(2, dtype=np.int64)}
    for side in ("left", "right"):
        payload[f"{side}_position"] = np.zeros((2, 6))
        payload[f"{side}_velocity"] = np.zeros((2, 6))
        payload[f"{side}_gripper"] = np.zeros((2, 2))
        payload[f"{side}_gripper_valid"] = np.ones(2, dtype=bool)
    np.savez_compressed(active, **payload)
    active_sha = hashlib.sha256(active.read_bytes()).hexdigest()
    meta = {"seed": 0, "episode": 0, "events": {"E3": 1}, "tape_sha256": source_sha}
    receipt = {
        "schema": "r22p19.stage2f.frozen_active_reference.v1", "status": "COMPLETE",
        "seed": 0, "episode": 0, "events": {"E3": 1}, "amplitude_m": 0.015,
        "axis": "e_perp", "both_arms_common_mode": True,
        "source_tape_sha256": source_sha, "command_count": 2, "npz_sha256": active_sha,
    }
    sidecar = active.with_suffix(".json")
    sidecar.write_text(json.dumps(receipt))
    loaded, loaded_receipt = FrozenActiveReference.load_validated(
        active, sidecar_path=sidecar, source_tape_path=source, source_meta=meta,
        expected_seed=0, expected_amplitude_m=0.015,
    )
    assert loaded.sha256 == active_sha and loaded_receipt == receipt
    receipt["axis"] = "wrong"
    sidecar.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="lineage mismatch"):
        FrozenActiveReference.load_validated(
            active, sidecar_path=sidecar, source_tape_path=source, source_meta=meta,
            expected_seed=0, expected_amplitude_m=0.015,
        )
