from stage2_robotwin.wrappers.event_detector import HandoverEventDetector


def _sample(step, left, right, open_command=False):
    return {
        "step": step,
        "time_s": step / 250.0,
        "left_contact": left,
        "right_contact": right,
        "donor_open_command": open_command,
    }


def test_complete_left_to_right_event_chain():
    detector = HandoverEventDetector("left", stable_steps=2)
    sequence = [
        _sample(0, True, False),
        _sample(1, True, True),
        _sample(2, True, True),
        _sample(3, True, True, True),
        _sample(4, False, True),
        _sample(5, False, True),
    ]
    for sample in sequence:
        detector.update(sample)
    audit = detector.audit()
    assert audit["valid"]
    assert audit["events"]["E1"]["step"] == audit["events"]["E2"]["step"]
    assert audit["events"]["E6"]["step"] == 5


def test_release_before_stable_receiver_is_invalid():
    detector = HandoverEventDetector("left", stable_steps=3)
    for sample in (
        _sample(0, True, False),
        _sample(1, True, True),
        _sample(2, True, True, True),
        _sample(3, False, True),
        _sample(4, False, True),
        _sample(5, False, True),
    ):
        detector.update(sample)
    assert not detector.audit()["valid"]
    assert "E3" in detector.audit()["missing"]
