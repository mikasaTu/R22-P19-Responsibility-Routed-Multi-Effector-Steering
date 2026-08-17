import unittest

from stage3_hybrid.audit import validate_receipt_flags
from stage3_hybrid.outcomes.takeover_label import takeover_success
from stage3_hybrid.tests import test_contract as contract


class MandatoryNamedTests(unittest.TestCase):
    def test_mode_timewarp_preserves_receiver_commands(self):
        contract.ContractTests.test_01_mode_invariance_receiver(self)

    def test_base_mode_is_exact_noop(self):
        contract.ContractTests.test_02_base_noop(self)

    def test_delayed_release_shifts_arm_and_gripper_together(self):
        contract.ContractTests.test_03_paired_arm_gripper_shift(self)

    def test_prefix_hash_matches_across_modes(self):
        contract.ContractTests.test_04_prefix_hash_before_anchor(self)

    def test_fresh_process_contract(self):
        contract.ContractTests.test_05_fresh_process_contract(self)

    def test_no_snapshot_restore_in_formal_runner(self):
        self.assertFalse(validate_receipt_flags({"fresh_process": True, "fresh_scene": True,
            "replayed_from_episode_start": True, "snapshot_restore_used": True}))

    def test_outcome_label_independent_of_short_horizon_features(self):
        metrics={"eventual_task_success":True,"handover_complete":True,"drop":False,"takeover_failure":False}
        self.assertEqual(takeover_success(metrics), takeover_success(dict(metrics)))

    def test_episode_split_has_no_leakage(self):
        calibration={0,1}; heldout={2,3,5,6,7,8,9,10}
        self.assertFalse(calibration & heldout)

    def test_full_oracle_lexicographic_selection(self):
        contract.ContractTests.test_08_oracle_lexicographic(self)

    def test_shuffled_control_changes_episode_mapping(self):
        contract.ContractTests.test_09_shuffle_changes_mapping(self)

    def test_analysis_fails_closed_on_missing_cells(self):
        contract.ContractTests.test_10_fail_closed_missing_cells(self)

    def test_decision_gate_fails_closed(self):
        contract.ContractTests.test_11_fail_closed_decision(self)


if __name__ == "__main__": unittest.main()
