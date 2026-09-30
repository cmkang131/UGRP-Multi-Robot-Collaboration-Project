"""Collect all T08a checks via the existing CI navigation glob; no CI edits."""
import pytest

pytest.register_assert_rewrite('test_beam_initial_pose_plan')
from test_beam_initial_pose_plan import *  # noqa: F403,E402
