import numpy as np
from harness.e2e_beam_avoidance import add,fallback
from harness.public_navigation_unknown import UnknownCostmap,UnknownNavigator


def test_observed_beam_costmap_is_transient_and_navfn_goes_around():
    original=UnknownCostmap(np.zeros((60,60),np.uint8),[-1.5,-1.5],.05)
    changed=add(original,[0.,0.],0.)
    assert not original.raw.any() and changed.raw[30,30]==254
    nav=UnknownNavigator();start=[-.8,0.,0.];goal=[.6,0.]
    path=np.asarray(nav.plan_to(changed,start,goal))
    assert len(path)>2 and np.max(abs(path[:,1]))>.15
    for a,b in zip(path,path[1:]):
        for u in np.linspace(0,1,20):
            xy=a+u*(b-a)
            assert not (abs(xy[0])<=.3 and abs(xy[1])<=.03)
    retry=fallback(nav,start,goal,[0.,0.],0.)
    assert retry and np.max(abs(np.asarray(retry)[:,1]))>.15


def test_large_or_nonfinite_beam_geometry_cannot_allocate_unbounded_grid():
    nav=UnknownNavigator()
    assert fallback(nav,[0.,0.,0.],[1e7,1e7],[0.,0.],0.)==[]
    assert fallback(nav,[0.,0.,0.],[float('nan'),0.],[0.,0.],0.)==[]
