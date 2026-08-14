import numpy as np
from stage2_robotwin.stage2d.operator.robotwin_effect import task_effect_joint_delta


def test_effect_mapper_symbol_is_callable():
    assert callable(task_effect_joint_delta)
    assert np.asarray([0.0, 0.0, 0.0, 0.0]).shape == (4,)

