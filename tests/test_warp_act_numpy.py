"""No physics/render: calibrated command math against the original SDK."""
import itertools
from scripts.warp_act_numpy import solve_grip_site_ik
from harness.visual_arm_v3 import solve_grip_site_ik as reference


def test_numpy_pitch_search_matches_frozen_sdk_acceptance_pwm_and_tie_order():
    for xyz in itertools.product([.11,.14,.17,.20,.23],[-.02,0.,.02],[.015,.03,.06,.095]):
        for pitch in [-90.,-75.,-66.,-50.]:
            values=[]
            for solve in (reference,solve_grip_site_ik):
                try:values.append(solve(xyz,preferred_pitch_deg=pitch,calibrated_grasp_only=False))
                except ValueError as error:values.append(str(error))
            assert values[0]==values[1],(xyz,pitch,values)
