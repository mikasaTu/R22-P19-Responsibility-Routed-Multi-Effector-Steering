from stage2_robotwin.stage2d.capacity.channel_capacity import score_channels
from stage2_robotwin.stage2d.operator.desired_responsibility_state import DesiredResponsibilityState


def _outcome(scale=1.0, contact=1.0, drop=False):
    return {"translation": [0.01 * scale, 0, 0], "rotation_vector": [0, 0, 0.02 * scale],
            "support_delta": 0.001 * scale, "contact_retention": [1.0, contact],
            "drop": drop, "task_progress": 0.01 * scale}


def test_capacity_channels_penalize_takeover_failure():
    good = score_channels(_outcome(), _outcome(0.9), 1)
    bad = score_channels(_outcome(), _outcome(0.1, contact=0, drop=True), 1)
    assert good.full > bad.full
    assert good.capable and not bad.capable


def test_state_machine_hysteresis_and_slew():
    state = DesiredResponsibilityState()
    first = state.update(0.8, 1.0, True)
    assert first == 0.18 and state.active
    state.update(0.6, 1.0, True)
    assert state.active
    state.update(0.4, 1.0, True)
    assert not state.active

