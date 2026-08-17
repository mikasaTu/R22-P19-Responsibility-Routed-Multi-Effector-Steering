import copy
import unittest

import numpy as np

from stage3_hybrid.baselines import oracle, validate_library
from stage3_hybrid.conditions import single_factor_conditions, two_factor_conditions
from stage3_hybrid.modes import MODE_BY_NAME, MODES, command_hash, compose_item, donor_source_step
from stage3_hybrid.ranker import feature_vector, shifted_mapping


class Tape:
    def __init__(self, n=300): self.n = n
    def __len__(self): return self.n
    def item(self, i):
        return {"step": i, "left_position": np.array([i, i + .1]),
                "left_velocity": np.array([i + .2, i + .3]),
                "right_position": np.array([-i, -i - .1]),
                "right_velocity": np.array([-i - .2, -i - .3]),
                "left_gripper": (float(i), .1), "right_gripper": (float(-i), .1)}


def cell(mode, success=False, drop=False, failure=False, slip=1., jerk=1., dev=1.):
    return {"mode": mode, "metrics": {"eventual_task_success": success, "drop": drop,
            "takeover_failure": failure, "peak_relative_slip_m": slip,
            "peak_object_linear_jerk": jerk, "donor_action_deviation_mean": dev}}


class ContractTests(unittest.TestCase):
    def test_01_mode_invariance_receiver(self):
        tape = Tape(); hashes = []
        for mode in MODE_BY_NAME:
            items = [compose_item(tape, i, "left", mode, 180)[0] for i in range(len(tape))]
            hashes.append(command_hash(items, "right"))
        self.assertEqual(len(set(hashes)), 1)

    def test_02_base_noop(self):
        tape = Tape()
        for i in range(len(tape)):
            item, source = compose_item(tape, i, "left", "M0_BASE", 180)
            self.assertEqual(source, i); np.testing.assert_array_equal(item["left_position"], tape.item(i)["left_position"])

    def test_03_paired_arm_gripper_shift(self):
        tape = Tape(); item, source = compose_item(tape, 100, "left", "M1_EARLY_100", 180)
        self.assertEqual(source, 200); self.assertEqual(item["left_gripper"], tape.item(source)["left_gripper"])
        np.testing.assert_array_equal(item["left_position"], tape.item(source)["left_position"])
        np.testing.assert_array_equal(item["left_velocity"], tape.item(source)["left_velocity"])

    def test_04_prefix_hash_before_anchor(self):
        tape = Tape(); anchor = max(50 + 25, 180 - 100); hashes = []
        for mode in MODE_BY_NAME:
            items = [compose_item(tape, i, "left", mode, 180)[0] for i in range(anchor)]
            hashes.append(command_hash(items, "left"));
        self.assertEqual(len(set(hashes)), 1)

    def test_05_fresh_process_contract(self):
        from stage3_hybrid.audit import validate_receipt_flags
        good={"fresh_process":True,"fresh_scene":True,"replayed_from_episode_start":True,"snapshot_restore_used":False}
        self.assertTrue(validate_receipt_flags(good)); bad=dict(good,snapshot_restore_used=True)
        self.assertFalse(validate_receipt_flags(bad))

    def test_06_outcome_independent_mode_definition(self):
        before = [(m.name, m.kind, m.offset) for m in MODES]
        _ = oracle([cell("M0_BASE"), cell("M2_EARLY_50", success=True)])
        self.assertEqual(before, [(m.name, m.kind, m.offset) for m in MODES])

    def test_07_no_feature_leakage(self):
        good = {"short_horizon_features": {"50": {"object_height_m": 1, "object_displacement_m": 0,
            "linear_speed": 0, "angular_speed": 0, "donor_contact": True,
            "receiver_contact": True, "donor_action_deviation_mean": 0}}}
        self.assertEqual(feature_vector(good, 50).shape, (7,))
        bad = copy.deepcopy(good); bad["short_horizon_features"]["50"]["drop"] = False
        with self.assertRaises(ValueError): feature_vector(bad, 50)

    def test_08_oracle_lexicographic(self):
        chosen = oracle([cell("M0_BASE", success=False, slip=0), cell("M1_EARLY_100", success=True, slip=100)])
        self.assertEqual(chosen["mode"], "M1_EARLY_100")

    def test_09_shuffle_changes_mapping(self):
        self.assertNotEqual([1, 2, 3], shifted_mapping([1, 2, 3]))

    def test_10_fail_closed_missing_cells(self):
        from stage3_hybrid.analyze import summarize
        with self.assertRaises(RuntimeError): summarize([{"condition": "x", "seed": 0, "repeat": 0, "mode": "M0_BASE", "metrics": {}}])

    def test_11_fail_closed_decision(self):
        from stage3_hybrid.audit import validate_final_decision
        validate_final_decision("NO_INFORMATIVE_FAILURE_SPACE")
        with self.assertRaises(ValueError): validate_final_decision("GO")

    def test_12_grid_and_baselines_exact(self):
        self.assertEqual(len(single_factor_conditions()), 14); self.assertEqual(len(two_factor_conditions()), 6)
        validate_library()


if __name__ == "__main__": unittest.main()
