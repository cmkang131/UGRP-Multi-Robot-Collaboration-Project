"""Static geometry/range adapter parity, not a new scan matcher."""
import numpy as np
from harness.mapbuild_amcl import StaticField,StaticAMCL,OPTION
from harness.mapbuild_amcl_vendor import algorithms as nav2
from tests.test_mapbuild10 import STATIC,CAL,REQ,ZONE


def test_field_extends_known_wall_support_without_extra_allowed_poses():
    s=dict(bounds_m=[-1,1,-1,1],obstacles=[dict(id='wall_west',center_m=[-1,0],half_extents_m=[.02,1])])
    old=StaticField(s);full=StaticField(s,full_wall_extent=True)
    np.testing.assert_array_equal(full.free,old.free)
    assert old.distances([[-1.03,0]])[0]==2.
    assert abs(full.distances([[-1.03,0]])[0]-.01)<1e-12
    assert full.distances([[-4,0]])[0]==2.
    np.testing.assert_allclose(full.distances([[0,0]]),old.distances([[0,0]]))


def test_sensor_range_uses_nav2_node_min_sensor_ceiling_and_original_stride():
    field=StaticField(STATIC);poses=np.array([[0,0,0]])
    pts=np.tile([0,.9],(96,1))
    value=nav2.likelihood(field,poses,pts,.2,range_max=4.)[0]
    assert abs(value-(1+96*(.5+.5/4)**3))<1e-12
    assert nav2.likelihood(field,poses,np.full((96,2),np.nan),.2,range_max=4.)[0]==1.


def test_new_profile_preserves_initial_proposals_and_qualification_gate():
    kw=dict(option=OPTION,seed=123,initial_prior_option='start_zone_prior_v1',initial_prior=ZONE)
    old=StaticAMCL(STATIC,CAL,REQ,profile='nav2_defaults_v1',**kw)
    new=StaticAMCL(STATIC,CAL,REQ,profile='nav2_rgb_field_v1',**kw)
    np.testing.assert_array_equal(new.particles,old.particles)
    assert new.sigma_hit==old.sigma_hit==.2 and new.range_max==4 and old.range_max==100
    assert not new.belief()['ready_for_handoff']
