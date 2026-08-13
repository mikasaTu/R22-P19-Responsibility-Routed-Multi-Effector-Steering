from stage2_robotwin.scripts.analyze_smoke import event_frame_index


def test_event_frame_index_accounts_for_extra_event_frames():
    steps = [0, 24, 25, 26, 26, 50]
    assert event_frame_index(0, steps) == 0
    assert event_frame_index(24, steps) == 1
    assert event_frame_index(25, steps) == 2
    assert event_frame_index(26, steps) == 3
    assert event_frame_index(50, steps) == 4
