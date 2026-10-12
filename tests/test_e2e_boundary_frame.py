import math
from types import SimpleNamespace
import numpy as np
import pytest
from harness import e2e_boundary_frame as m
from harness import e2e_boundary_views as views
from harness.self_odom_grid import transform


def test_static_unregistered_live_path_is_closed():
    assert views.install(object()) is not None
    with pytest.raises(ValueError,match='REGISTRATION_REQUIRED'):
        views.install(object(),views.STANDOFF_OPTION)


def test_projection_uses_only_calibration_and_known_size(monkeypatch):
    from harness import e2e_b_standoff as static
    def denied(*a,**kw):raise AssertionError('STATIC_GEOMETRY_FORBIDDEN')
    for name in ('load_board','plan_standoffs','static_costmap','sight_clear'):
        monkeypatch.setattr(static,name,denied)
    m.framing.cache_clear()
    p=m.poses([1.,2.],[0.,0.,.3])
    assert p and all(math.hypot(x-1,y-2)>.8 for x,y,_ in p)
    assert not m.framing(.8)


def test_private_se2_transform_preserves_relative_candidate_geometry():
    center=np.array([1.,2.]);pose=np.array([.2,.3,.4]);tf=[7.,-4.,1.1]
    p=np.asarray(m.poses(center,pose))
    q=np.asarray(m.poses(transform([center],tf)[0],[*transform([pose[:2]],tf)[0],pose[2]+tf[2]]))
    np.testing.assert_allclose(q[:,:2],transform(p[:,:2],tf),atol=1e-12)
    np.testing.assert_allclose(q[:,2],p[:,2]+tf[2],atol=1e-12)


def test_navigator_plans_in_transformed_own_frame_once(monkeypatch):
    from tests.test_e2e_boundary_views import fixture
    n,g,c=fixture();n.option=views.STANDOFF_OPTION;n.boundary_frame=m.OPTION
    g.explorer.map_to_odom=np.array([2.,-1.,.7]);seen={}
    def candidates(center,pose):seen['center']=center;return [[3.,4.,.8]]
    def choose(*args,**kw):seen['poses']=kw['standoff'];return None
    monkeypatch.setattr(m,'poses',candidates);monkeypatch.setattr(views,'choose_view',choose)
    n.core.frontiers=lambda *args:[]
    n.update(c,np.zeros(3),1.)
    np.testing.assert_allclose(seen['center'],transform([[1.,0.]],g.explorer.map_to_odom)[0])
    assert seen['poses']==[[3.,4.,.8]] and not g.e2e_gate.references


def test_live_robot_receives_explicit_own_frame_option():
    import json
    from pathlib import Path
    from harness.e2e_live_mapping import Robot
    from harness.s4_event_policy import Options
    cov=json.loads(Path('configs/e2e_nees_egomap70_dev_v1.json').read_text())
    r=Robot('r1',61009,cov,Options(),exploration_progress='frontier_progress_v1',
        boundary_views=views.STANDOFF_OPTION,boundary_frame=m.OPTION)
    assert r.goal.explorer.navigator.boundary_frame==m.OPTION
