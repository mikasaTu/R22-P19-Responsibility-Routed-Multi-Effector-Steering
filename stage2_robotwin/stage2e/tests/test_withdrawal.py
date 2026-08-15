import numpy as np

from stage2_robotwin.stage2e.withdrawal.branch_isolation import randomized_cells
from stage2_robotwin.stage2e.withdrawal.common import retention_command


def test_randomized_cells_are_complete_and_deterministic():
    first = randomized_cells([0, 1, 2], ["motion", "support"], [1.0, 0.0], 2, 7)
    second = randomized_cells([0, 1, 2], ["motion", "support"], [1.0, 0.0], 2, 7)
    assert first == second and len(first) == 24
    assert [cell.launch_index for cell in first] == list(range(24))


def test_retention_zero_is_real_open_target():
    assert retention_command((0.0, 0.1), 1.0)[0] == 0.0
    assert retention_command((0.0, 0.1), 0.0)[0] == 1.0
    values = [retention_command((0.0, 0.1), fade)[0]
              for fade in (1.0, 0.75, 0.5, 0.25, 0.0)]
    assert np.all(np.diff(values) >= 0)
