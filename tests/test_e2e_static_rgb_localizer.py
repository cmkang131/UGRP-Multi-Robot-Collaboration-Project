import numpy as np
from harness.e2e_static_rgb_localizer import create


def arena():
    return dict(bounds_m=[-1.,1.,-1.,1.], obstacles=[dict(kind='wall',center_m=[0.,-.8],half_extents_m=[1.,.1])])


def test_uniform_prior_has_no_start_pose_hint_and_is_seed_reproducible():
    a=create(arena(),option='static_walls_v1',seed=4);b=create(arena(),option='static_walls_v1',seed=4)
    assert np.array_equal(a.px,b.px)
    assert (a.field.distances(a.px[:,:2])>.15).all()
    assert np.ptp(a.px[:,0])>1.9 and np.ptp(a.px[:,2])>6.
    assert a.n==2000


def test_no_observation_does_not_fabricate_a_measurement():
    pf=create(arena(),option='static_walls_v1',seed=9)
    r=pf.step(t=0.,points=[],delta=[0.,0.,0.],servo={3:740,4:2320,5:1320,6:1500},features=[])
    assert r['updates']==0 and r['reason']=='no_points' and not r['resolved']
    assert r['initial_pose_source']=='uniform_static_free_space'
