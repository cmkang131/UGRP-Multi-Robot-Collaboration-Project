"""Shared visible-only teacher factory for pairact P1 tests (same as test_beamact5_r3_modes.teacher)."""
from scripts.replay_grasp_act_recovery import KW
from scripts.zone_teacher import FOLDED
from sim.grasp_act_teacher_v3 import VisibleOnlyGraspTeacher


def teacher(**kwargs):
    t = VisibleOnlyGraspTeacher('r1', 'teal', FOLDED, **KW,
                                approach_recovery='progress_view_recovery_v3', **kwargs)
    t.folded_ready = True
    return t
