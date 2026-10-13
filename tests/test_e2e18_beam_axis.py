import copy,math
import numpy as np
import pytest
from harness.e2e_beam_axis import error
from tests.test_e2e18_route_guard import goal,route
from harness.zone_study_contract import ContractViolation


def test_opposite_end_is_same_axis_but_off_stays_strict():
    g=goal()
    with pytest.raises(ContractViolation,match='BEAM_ALIGNMENT'):route(g,math.pi)
    a=route(g,0.)
    g=goal();g.e2e_beam_axis='undirected_v1';b=route(g,math.pi)
    assert a['route']['waypoints']==b['route']['waypoints']
    assert g.e2e_route_diagnostics['beam_pose_own_m'][2]==math.pi
    assert g.e2e_route_diagnostics['beam_axis_error_rad']==pytest.approx(0.,abs=1e-14)
    with pytest.raises(ContractViolation,match='BEAM_ALIGNMENT'):route(g,math.pi/2)


def test_axis_tolerance_and_directed_center_geometry():
    assert error(math.radians(-177.385),'undirected_v1')==pytest.approx(math.radians(2.615))
    for deg in (8.,172.,-172.,90.):assert error(math.radians(deg),'undirected_v1')>math.radians(5)
    assert error(math.pi)==math.pi
    with pytest.raises(ValueError):error(0.,'bad')


def test_registered_axis_bundle_and_profile_check():
    from scripts.run_e2e_ownmap_live import bundle
    from tests.test_e2e18 import options,ROOT
    from harness.e2e_runtime_registration import require_current
    b=bundle('a'*40,61004,'study_gemma4_31b_v1',**options(),speed5='lean_v3',observation_cadence='on_v1',route_guard='dev_nominal_v1',beam_axis='undirected_v1')
    assert b['execution_bundle_id']=='e2e18-v222';require_current(b,ROOT)
    b['e2e_options']['beam_axis']='off'
    with pytest.raises(ValueError,match='UNDIRECTED'):require_current(b,ROOT)
