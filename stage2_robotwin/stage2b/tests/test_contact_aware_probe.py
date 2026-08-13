from types import SimpleNamespace

import numpy as np
import pytest

from stage2_robotwin.stage2b.intervention.follower_mode import (
    parallel_follower_displacement,
)
from stage2_robotwin.stage2b.intervention.paired_authority_profiles import (
    ContactAwareAuthorityProbe,
    gamma_label,
)
from stage2_robotwin.stage2b.intervention.task_frame import ObjectTaskFrame


def test_task_frame_separates_horizontal_transport_from_vertical_support():
    frame = ObjectTaskFrame.from_points([0, 0, 1.0], [2, 2, 0.5])
    np.testing.assert_allclose(frame.e_parallel, np.asarray([1, 1, 0]) / np.sqrt(2))
    np.testing.assert_allclose(frame.e_vertical, [0, 0, 1])
    np.testing.assert_allclose(frame.matrix().T @ frame.matrix(), np.eye(3), atol=1e-12)
    assert frame.audit()["orthonormal_at_1e-12"]


def test_follower_moves_only_parallel_and_gamma_retains_error_ratio():
    displacement = parallel_follower_displacement(
        object_displacement_world=[0.01, 0.02, -0.03],
        e_parallel_world=[1, 0, 0],
        gamma=0.4,
    )
    np.testing.assert_allclose(displacement, [0.006, 0, 0], atol=1e-12)


def test_follower_gamma_fails_closed_outside_unit_interval():
    with pytest.raises(ValueError, match="gamma"):
        parallel_follower_displacement([0, 0, 0], [1, 0, 0], 1.1)


def test_probe_uses_e4_anchored_inclusive_window_and_matched_profiles():
    probe = ContactAwareAuthorityProbe(
        reference_e4=1000,
        reference_e5=1300,
        gammas=[0.6, 0.2],
        horizons=[10, 5],
        stride=25,
    )
    assert probe.sample_steps[0] == 750
    assert probe.sample_steps[-1] == 1150
    assert len(probe.sample_steps) == 17
    assert probe.should_sample(1000, {})
    assert not probe.should_sample(1001, {})
    profiles = probe._profiles()
    assert [(item.driver, item.follower) for item in profiles] == [
        ("left", "right"),
        ("right", "left"),
        ("left", "right"),
        ("right", "left"),
    ]
    assert probe.contract()["both_grippers_held"] is True


def test_window_end_is_e4_plus_150_when_contact_loss_is_later():
    probe = ContactAwareAuthorityProbe(reference_e4=4083, reference_e5=4555)
    assert probe.window_start == 3833
    assert probe.window_end == 4233


def test_gamma_label_is_stable_for_artifact_names():
    assert gamma_label(0.6) == "0p6"
    assert gamma_label(0.05) == "0p05"
