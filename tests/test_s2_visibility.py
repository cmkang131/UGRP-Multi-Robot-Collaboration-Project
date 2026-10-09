import copy
import json
from types import SimpleNamespace as NS
import numpy as np
import pytest
from test_solo_cyan_v106 import static, cal, FakePose, FakeVision, rt
from test_s2_visual_fix import make_provider
from test_s2_likelihood_field import observation
from harness.zone_solo_cyan_visibility import box_depth, robot_boxes, Visibility, PARAMS, pixel_rays
from harness.zone_solo_cyan_likelihood_field import Runtime, Previous, install
from harness import zone_s2_realism_contract_v123 as c


def test_default_and_off_actions_record_identical(static, cal):
    rs=[cls(static,None,None,provider_factory=lambda *a,**k:FakePose(copy.deepcopy(cal)),vision_factory=FakeVision,**kw)
        for cls,kw in [(Previous,{}),(Runtime,{}),(Runtime,dict(visibility_mask='off'))]]
    try:
        for r in rs:
            r.initial_commands(0.,{'r3':{1:1500,**rt.high.HIGH}});r.last_report=r.pose.report(1.);r.state='carry';r.receipt=True
        for t in (1.,1.05,1.1,1.2,1.65,1.8):
            actions=[r.step(t) for r in rs]
            assert len(set(json.dumps(x).encode() for x in actions))==1
            for r,rows in zip(rs,actions):
                for rid,a in rows:r.on_command(rid,t,a)
        assert len(set(json.dumps(r.record()).encode() for r in rs))==1
    finally:
        for r in rs:r.close()


def test_ray_box_shadow_parallel_inside_and_behind():
    pytest.importorskip("mujoco", reason="Engine import closure; exercised in ubuntu-simulation-runtime")
    r=np.array([[0,0,1],[1,0,1],[0,0,-1]])
    d=box_depth(np.zeros(3),r,np.array([0,0,2]),np.eye(3),np.array([.5,.5,.5]))
    np.testing.assert_equal(d,[1.5,np.inf,np.inf])
    assert box_depth(np.zeros(3),r[:1],np.zeros(3),np.eye(3),np.ones(3))[0]==0
    boxes=robot_boxes({1:1500,**rt.high.HIGH})
    assert set(b[0] for b in boxes)=={'gripper','arm','chassis'}
    assert all(np.isfinite(b[1]).all() and (b[3]>0).all() for b in boxes)


def test_missing_visibility_is_prediction_only_not_new_fix():
    sources=[make_provider() for _ in range(2)]
    try:
        a,b=[s[1] for s in sources];vl=sources[0][2]
        a.t=b.t=2.;obs=observation(a,vl,0.)
        v=Visibility();v.depth_image=lambda cm,pose:np.full((480,len(cm.columns)),np.inf)
        # All prior-predicted wall bottoms below view. The observed image edge
        # must not become a max-range hit or change the posterior.
        a.expected=lambda px,pose:(np.full((len(px),len(a.columns)),600.),None)
        stats=install(a,c.old.hp.resolve(c.old.MAP_ID)[0],visibility=v)
        a.update_obs(2.,obs,rt.high.HIGH);b.update_obs(2.,None,rt.high.HIGH)
        np.testing.assert_array_equal(a.px,b.px);np.testing.assert_array_equal(a.logw,b.logw)
        assert a.last_scan_t==b.last_scan_t and stats['updates']==0 and v.audit['rows'][-1]['kept']==0
    finally:
        for src,_,_ in sources:src.close()


def test_clear_columns_update_but_shadow_and_cargo_are_unknown():
    src,pf,vl=make_provider()
    try:
        pf.init_gaussian((1.6,1.,0.),(.01,.01,.01));pf.t=2.
        obs=observation(pf,vl,0.);v=Visibility()
        depth=np.full((480,len(pf.columns)),np.inf)
        v.depth_image=lambda cm,pose:depth
        clean=v.apply(pf,obs,rt.high.HIGH,2.)
        assert clean is not None and clean.informative.sum()>=6
        depth[:,:]=0
        assert v.apply(pf,obs,rt.high.HIGH,2.1) is None
        depth[:,:]=np.inf;v.cargo=np.ones((480,640),bool)
        assert v.apply(pf,obs,rt.high.HIGH,2.2) is None
        v.cargo=None;stats=install(pf,c.old.hp.resolve(c.old.MAP_ID)[0],visibility=v)
        assert pf.update_obs(2.3,obs,rt.high.HIGH)['measured'] and stats['updates']==1
    finally:src.close()


def test_command_geometry_mask_and_preregistered_parameters():
    pytest.importorskip("mujoco", reason="Engine import closure; exercised in ubuntu-simulation-runtime")
    src,pf,vl=make_provider()
    try:
        cm=pf.column_model_for(rt.high.HIGH);v=Visibility()
        d=v.depth_image(cm,{1:1500,**rt.high.HIGH})
        assert d.shape==(480,len(pf.columns)) and np.isinf(d).any()
        assert v.depth_image(cm,{1:1500,**rt.high.HIGH}) is d
        spec=json.load(open(c.ROOT/'experiments/2026-10-06-s2-realism/visibility-criteria.json'))
        assert PARAMS['robot_padding_m']==spec['robot_geometry_padding_m']
        assert PARAMS['prior_visible_probability']==spec['minimum_prior_visible_probability']
        assert PARAMS['rows_px']==spec['visible_rows_px']
        assert PARAMS['cargo_padding_px']==spec['cargo_mask_padding_px']
    finally:src.close()


def test_diagnostic_projection_and_wall_occlusion_have_known_geometry():
    import importlib.util
    path=c.ROOT/'experiments/2026-10-06-s2-realism/analyze_visibility.py'
    spec=importlib.util.spec_from_file_location('visibility_geometry',path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    cm=NS(origin=np.array([0.,0.,1.]),_rot=np.array([[0,0,1],[-1,0,0],[0,-1,0]]),columns=np.array([m.K[0,2]]))
    static={'obstacles':[dict(kind='wall',center_m=[2,0],half_extents_m=[.1,1.],height_m=2.)]}
    rows,points,depth=m.bottom_projection(cm,[0,0,0],m.wall_segments(static))
    np.testing.assert_allclose(points,[[1.9,0,0]])
    np.testing.assert_allclose(rows,[m.K[1,2]+m.K[1,1]/1.9])
    rays=(points-cm.origin)/depth[:,None]
    np.testing.assert_allclose(m.wall_depths(cm,[0,0,0],rays,static),depth)
    static['obstacles'].append(dict(kind='wall',center_m=[1,0],half_extents_m=[.1,1.],height_m=2.))
    assert m.wall_depths(cm,[0,0,0],rays,static)[0]<depth[0]
