import numpy as np
import pytest

from stage2_robotwin.stage2c.replay.tape import ExpertTape


def _records():
    return [
        {
            "step": index,
            "left_position": np.full(6, index),
            "left_velocity": np.zeros(6),
            "right_position": np.full(6, -index),
            "right_velocity": np.zeros(6),
            "left_gripper": None if index == 0 else (0.1, 0.02),
            "right_gripper": None,
        }
        for index in range(3)
    ]


def test_tape_roundtrip_and_none_gripper(tmp_path):
    path = tmp_path / "tape.npz"
    ExpertTape.from_records(_records()).save(path)
    tape = ExpertTape.load(path)
    assert len(tape) == 3
    assert tape.item(0)["left_gripper"] is None
    assert tape.item(1)["left_gripper"] == (0.1, 0.02)
    assert len(tape.target_sequence(0, 2)) == 2


def test_tape_rejects_noncontiguous_steps():
    records = _records()
    records[2]["step"] = 4
    with pytest.raises(ValueError, match="contiguous"):
        ExpertTape.from_records(records)
