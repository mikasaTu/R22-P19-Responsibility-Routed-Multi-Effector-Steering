from stage2_robotwin.stage2e.conformance.method_registry import METHODS, get_method
from stage2_robotwin.stage2e.conformance.runtime_receipt import RuntimeReceipt


def test_registry_has_unique_names_and_required_fields():
    assert len(METHODS) == len(set(METHODS))
    assert all(spec.name == name for name, spec in METHODS.items())
    assert get_method("W0_BASE").expected_solver_calls == 0


def test_runtime_receipt_fails_closed_on_action_mismatch():
    receipt = RuntimeReceipt(get_method("W2_MOTION_WITHDRAWAL"))
    assert not receipt.validate()["valid"]
    receipt.record_action_modification("motion")
    assert receipt.validate()["valid"]
