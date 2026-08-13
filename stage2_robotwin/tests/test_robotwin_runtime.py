import pytest

from stage2_robotwin.wrappers.robotwin_runtime import build_handover_block


def test_rejects_implicit_or_unknown_planner_substitution():
    with pytest.raises(ValueError, match="unsupported Stage-2 planner"):
        build_handover_block("/not/consulted", planner="curobo")
