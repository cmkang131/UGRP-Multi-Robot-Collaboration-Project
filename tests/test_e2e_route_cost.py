import math
import numpy as np
from scipy.ndimage import binary_dilation
from harness.e2e_route_cost import blocked,configure,OPTION
from harness.own_map_navigation import ObservedGrid,PAIR_FOOTPRINT,footprint_clearance


def test_random_rotated_footprints_match_existing_occupied_and_unknown_dilation():
    rng=np.random.default_rng(17)
    for shape in ((17,21),(48,61)):
        state=rng.choice([-1,0,1],size=shape,p=[.95,.025,.025])
        for margin in (.02,.3,1.4):
            for yaw in (0.,.37,math.pi/2):
                r=.1;n=math.ceil((PAIR_FOOTPRINT.radius+margin)/r+.71)
                y,x=np.mgrid[-n:n+1,-n:n+1]*r;c,s=math.cos(yaw),math.sin(yaw)
                kernel=(abs(c*x+s*y)<=PAIR_FOOTPRINT.half_length_m+margin+r*.71)&(abs(-s*x+c*y)<=PAIR_FOOTPRINT.half_width_m+margin+r*.71)
                np.testing.assert_array_equal(blocked(state,kernel),binary_dilation(state!=-1,structure=kernel,border_value=1))


def test_huge_uncertainty_impossible_footprint_returns_all_blocked_without_dilation(monkeypatch):
    import cv2
    monkeypatch.setattr(cv2,'dilate',lambda *a,**k:(_ for _ in ()).throw(AssertionError('unnecessary dilation')))
    assert blocked(-np.ones((31,42),np.int8),np.ones((101,101),bool)).all()


def test_real_grid_and_native_views_use_identical_bounds():
    from types import SimpleNamespace
    from harness.e2e_route_coverage import NativeView
    g=ObservedGrid('r1',.1);g.initial_support();g.observe(robot_id='r1',frame_id=1,pose=[0,0,0],floor_xy=[[.5,.2],[.8,0]],wall_xy=[[1.,0]])
    old=footprint_clearance(g,PAIR_FOOTPRINT,.02,yaw=.37)
    configure(SimpleNamespace(explorer=SimpleNamespace(grid=g)),OPTION)
    new=footprint_clearance(g,PAIR_FOOTPRINT,.02,yaw=.37)
    for a,b in zip(old,new):np.testing.assert_array_equal(a,b)
    assert NativeView(g)._clearance_bounds_v1


def test_v228_registers_both_pending_phase_and_clearance_options():
    from scripts.run_e2e_ownmap_live import bundle
    from tests.test_e2e18 import options,ROOT
    from harness.e2e_runtime_registration import require_current
    b=bundle('a'*40,61003,'study_gemma4_31b_v1',**options(),speed5='lean_v3',observation_cadence='on_v1',route_guard='dev_nominal_v1',beam_axis='undirected_v1',route_coverage='native_v1',carrier_axes='beam_v1',carrier_approach='standoff_v1',route_extent='goal_envelope_v1',record_scalars='python_v1',pose_guard='se2_innovation_v1',protocol_recovery='envelope_retry_v1',camera_load='nominal_command_v1',route_tokens='1600_v1',protocol_progress='stage_retry_v1',route_cost=OPTION)
    require_current(b,ROOT);assert b['execution_bundle_id']=='e2e18-v228'
    assert 'harness/e2e_route_cost.py' in b['source_sha256']
    assert 'harness/e2e_protocol_progress.py' in b['source_sha256']
