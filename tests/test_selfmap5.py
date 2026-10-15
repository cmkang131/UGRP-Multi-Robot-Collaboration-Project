"""Own-observation numerical/scheduler regression tests; no simulator imports."""
import ast
import copy
from dataclasses import replace
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from harness import self_map_integration as sm
from harness import self_map_executor as ex
from harness import selfmap4_geometry as g
from harness import selfmap5_revision as rev
from harness import selfmap5_registration as reg
from scripts import run_self_map_diagnostic as run
from test_self_map_integration import fixture_mapper, receive
from test_self_map_executor import Sweep, step


def test_default_off_invalid_and_profile_dependencies():
    assert sm.Options().revision_gate == sm.Options().multiframe_registration == 'off'
    for key, value in [('revision_gate', rev.OPTION), ('multiframe_registration', reg.OPTION)]:
        with pytest.raises(ValueError, match='REQUIRES_RECOVERY'):
            sm.Options(**{key:value})
        with pytest.raises(ValueError, match='UNKNOWN'):
            sm.Options(**{key:'on'})
    old = run.bundle('a'*40, 1, 30)
    assert not any(k in old['options'] for k in ('revision_gate','multiframe_registration','render_profile'))
    new = run.bundle('a'*40, 1, 30, recovery_profile=g.PROFILE,
        revision_gate=rev.OPTION, multiframe_registration=reg.OPTION, render_profile='floor_light_textured_v1')
    assert new['dependencies'][0]['pr'] == 511
    assert new['options']['wall_texture'] == 'off' and new['weld'] is False
    assert new['scene_version'] == 'floor_light_textured_v1' and not new['pool_with_previous_results']


def test_correct_yaw_correction_above_old_gate_is_within_predicted_innovation():
    covariance = np.diag([.07**2, .07**2, math.radians(4.4)**2])
    test = rev.revision_test([0,0,0], [.042,0,math.radians(-6.38)], covariance)
    assert not test['required'] and test['mahalanobis'] < 1.6
    assert rev.revision_test([0,0,0], [.3,0,0], covariance)['required']
    # Correlation matters; diagonal-only normalization would admit this.
    c = np.array([[1., .99, 0], [.99, 1., 0], [0,0,1.]])
    assert rev.revision_test([0,0,0], [1,-1,0], c)['required']


def test_innovation_wrap_and_singular_axis_fail_closed():
    assert not rev.revision_test([0,0,math.pi-.01], [0,0,-math.pi+.01], np.eye(3))['required']
    assert rev.revision_test([0,0,0], [.01,0,0], np.zeros((3,3)))['required']
    assert not rev.revision_test([0,0,0], [0,0,0], np.zeros((3,3)))['required']
    assert not rev.revision_test([0,0,0], [.0014,-.0009,.0011], np.zeros((3,3)),
        measurement_covariance=np.eye(3)*.005**2)['required']
    with pytest.raises(ValueError, match='PSD'):
        rev.revision_test([0,0,0], [0,0,0], -np.eye(3))


def segment():
    return [dict(observation=SimpleNamespace(frame_id=i), source=source,
        pose=np.array([float(i),0.,0.]), distance_since_visual=distance,
        rays=dict(camera=[0,0], segments=[[[1.,-.3],[1.,.3]]], floor_xy=[[.5,0.]]))
        for i,source,distance in [(1,'bootstrap',0.),(2,'visual_update',0.),
                                 (3,'command_only',1.),(4,'command_only',3.)]]


def test_partial_pose_rebuild_is_distance_weighted_and_preserves_visual_prefix():
    h=segment(); original=copy.deepcopy(h)
    r=dict(anchor_frame_id=2, prior=[5,0,0], corrected=[5.4,0,0], distance=4.)
    poses, error=rev.partial_poses(h,r)
    assert error is None
    np.testing.assert_array_equal(poses[0],h[0]['pose'])
    np.testing.assert_array_equal(poses[1],h[1]['pose'])
    assert poses[2][0] == pytest.approx(3.1) and poses[3][0] == pytest.approx(4.3)
    assert rev.issued_distance([0,0,1]) == pytest.approx(.15)
    for a,b in zip(h,original): np.testing.assert_array_equal(a['pose'],b['pose'])
    assert rev.partial_poses(h,dict(r,distance=0))[1] == 'zero_command_distance'
    assert rev.partial_poses(h[:2],dict(r,distance=0))[1] == 'zero_command_distance'
    assert rev.partial_poses(h,dict(r,anchor_frame_id=1))[1] == 'non_command_record_after_anchor'


def test_partial_rebuild_raster_is_atomic_and_does_not_call_orb(monkeypatch):
    mapper,_=fixture_mapper(monkeypatch)
    mapper.options=replace(mapper.options,recovery_profile=g.PROFILE,revision_gate=rev.OPTION)
    mapper.history=segment();mapper.prior_frames={3,4};mapper.rebuild_required=True
    mapper.pending_revision=dict(anchor_frame_id=2,prior=[5,0,0],corrected=[5.4,0,0],distance=4.)
    monkeypatch.setattr(mapper.slam,'_fit',lambda *a:pytest.fail('ORB history refit'))
    receipt=mapper.rebuild(3)
    assert receipt['committed'] and receipt['refitted']==2 and receipt['preserved']==2
    assert mapper.grid.navigation.seen=={1,2,3,4} and not mapper.rebuild_required
    assert mapper.prior_frames=={3,4}  # command reconstruction is not visual proof
    before=copy.deepcopy(mapper.grid.navigation.odds)
    mapper.rebuild_required=True;mapper.pending_revision=dict(anchor_frame_id=2,prior=[5,0,0],corrected=[6,0,0],distance=0.)
    assert not mapper.rebuild(9)['committed']
    assert mapper.grid.navigation.odds==before and mapper.rebuild_required


def test_static_world_revision_remains_quarantined(monkeypatch):
    mapper,_=fixture_mapper(monkeypatch)
    mapper.options=replace(mapper.options,recovery_profile=g.PROFILE,revision_gate=rev.OPTION)
    mapper.recovery=True;mapper.rebuild_cause='static_frame_correction';mapper.rebuild_required=True
    receipt=mapper.rebuild(3)
    assert not receipt['committed'] and mapper.rebuild_required
    assert mapper.rebuild_cooldown()==5.
    assert mapper.rebuild(4)['deferred']


def test_recovery_deadline_allows_two_full_sweeps(monkeypatch):
    mapper,state=fixture_mapper(monkeypatch)
    mapper.options=replace(mapper.options,recovery_profile=g.PROFILE,revision_gate=rev.OPTION)
    c=ex.SelfMapExecutor('r1',mapper=mapper,sweep=Sweep(),cap_s=180.)
    c.stage='select';state['blank']=True
    step(c,1,1.)
    assert c.recovery_started==1.
    step(c,2,22.)
    assert not c.done  # old policy terminated at 21
    command,trace=step(c,3,81.)
    assert c.done and command['kind']=='hold' and not trace['complete']
    assert rev.RECOVERY_DEADLINE_S >= 2*(len(ex.PANS)+30+1)
    assert rev.REBUILD_COOLDOWN_S < rev.RECOVERY_DEADLINE_S/2


def edges_and_lines():
    edges=[dict(a=np.array([0.,0.]),b=np.array([2.,0.]),normal=np.array([0.,1.]),hue=50),
           dict(a=np.array([0.,0.]),b=np.array([0.,2.]),normal=np.array([1.,0.]),hue=50)]
    return edges,[dict(kind='floor_line',endpoints=[e['a'],e['b']],normal=e['normal'],hue=e['hue']) for e in edges]


def test_multiframe_axes_use_relative_slam_and_expire_at_sweep_boundary():
    e,lines=edges_and_lines();m=reg.MultiFrameEvidence();cov=np.diag([.02**2]*3)
    m.add(dict(features=lines),[0,0,0],0)
    assert m.frames==[]
    m.begin(0);m.add(dict(features=[lines[0]]),[0,0,0],0)
    assert m.supported(e,[0,0,0],[0,0,0],cov)[1]['independent_axis_count']==1
    # Same world line seen after 90deg body turn: transform into that body frame.
    line=copy.deepcopy(lines[1]); line['endpoints']=[[0,0],[2,0]];line['normal']=[0,-1]
    m.add(dict(features=[line]),[0,0,math.pi/2],1)
    supported,detail=m.supported(e,[0,0,math.pi/2],[0,0,math.pi/2],cov)
    assert supported and detail['independent_axis_count']==2 and detail['evidence_frames']==2
    m.end();assert not m.supported(e,[0,0,0],[0,0,0],cov)[0]
    m.begin(0);m.add(dict(features=lines),[0,0,0],31)
    assert not m.active and not m.frames


def test_parallel_axes_wrong_color_and_covariance_scaled_residual():
    e,lines=edges_and_lines();m=reg.MultiFrameEvidence();m.begin(0)
    for t in range(3):m.add(dict(features=[lines[0]]),[0,0,0],t)
    assert m.supported(e,[0,0,0],[0,0,0],np.eye(3)*1e-5)[1]['independent_axis_count']==1
    m.begin(0);m.add(dict(features=lines),[0,0,0],0)
    assert not m.supported(e,[.2,.2,0],[0,0,0],np.eye(3)*1e-5)[0]
    assert m.supported(e,[.2,.2,0],[0,0,0],reg.calibrated_covariance(np.eye(3)*.04**2))[0]
    wrong=copy.deepcopy(lines);[f.update(hue=100) for f in wrong]
    m.begin(0);m.add(dict(features=wrong),[0,0,0],0)
    assert not m.supported(e,[0,0,0],[0,0,0],np.eye(3))[0]


def test_pf_augmented_recovery_reinjects_high_ess_collapsed_cloud():
    n=2000
    pf=SimpleNamespace(n=n,px=np.zeros((n,3)),logw=np.zeros(n),rng=np.random.default_rng(42),
        stats={'resamples':0},_weights=lambda:np.ones(n)/n,
        _uniform_free=lambda n:np.ones((n,3))*2.)
    p=reg.RecoveryPolicy();p.measure(pf,np.ones(n)/n,np.zeros(n),{3:740,4:2320,5:1320,6:1500},False)
    row=p.measure(pf,np.ones(n)/n,np.ones(n)*-20,{3:740,4:2320,5:1320,6:1500},False)
    assert row['ess']>n/2 and row['injection_probability']>0 and row['injected']>0
    assert row['alpha_slow']==.001 and row['alpha_fast']==.1
    assert (pf.px[:,0]==2.).sum()==row['injected']


def test_registration_needs_three_distinct_fresh_views_and_uses_inflated_cov(monkeypatch):
    static,_=g.static_input();r=g.StaticRegistration(static,multiframe_registration=reg.OPTION)
    e,lines=edges_and_lines();r.pf.landmark_map.edges=e
    raw=np.eye(3)*.0001
    output=dict(pose=[0.,0.,0.],covariance=raw.tolist(),updated=True,resolved=True,cluster={'mass':1.},sensor={})
    monkeypatch.setattr(r.pf,'step',lambda **kw:copy.deepcopy(output))
    r.begin_sweep(0)
    obs=dict(features=lines,segments=[])
    for t in range(3):r.step(obs,[0,0,0],{6:1500},t,[0,0,0])
    assert len(r.confirmations)==1 and r.map_from_own is None
    r.step(obs,[0,0,0],{6:1750},3,[0,0,0])
    assert len(r.confirmations)==2
    assert r.step(obs,[0,0,0],{6:2000},4,[0,0,0]) is not None
    assert r.map_from_own is not None and len(r.confirmations)==3
    np.testing.assert_allclose(r.last['covariance'],reg.calibrated_covariance(raw))
    r.begin_sweep(5)
    r.step(dict(features=[],segments=[]),[0,0,0],{6:2000},5,[0,0,0])
    assert len(r.confirmations)==0


def test_texture_selection_source_routes_install_and_audits_without_importing_plant():
    # AST inspection deliberately avoids importing modules that import MuJoCo.
    root=Path(__file__).resolve().parents[1]
    for path in ('sim/wall_parallax_strafe.py','sim/active_wall_map.py','sim/solo_cyan_v106.py'):
        tree=ast.parse((root/path).read_text())
        assert any(isinstance(n,ast.Constant) and n.value=='render_profile' for n in ast.walk(tree))
    assert 'base_profile=profile' in (root/'sim/active_wall_map.py').read_text()


def test_receive_uses_prediction_plus_fit_innovation_instead_of_insertion_sigma(monkeypatch):
    mapper,state=fixture_mapper(monkeypatch)
    receive(mapper,1)
    mapper.options=replace(mapper.options,recovery_profile=g.PROFILE,revision_gate=rev.OPTION,
                           pose_rebuild='refit_history_v1')
    # Isolate the revision seam from the independent static PF input adapter.
    mapper.slam.covariance=np.diag([.07**2,.07**2,math.radians(4.4)**2])
    state['pose']=np.array([.042,0.,math.radians(6.38)])
    row=receive(mapper,2)
    assert row['pose_source']=='visual_update'
    assert not row['revision_innovation']['required'] and not row['rebuild_required']
    assert row['map_updated']


def test_queue_is_deny_by_default_for_every_scene_and_stage():
    from scripts.prepare_selfmap5_queue import make_queue
    q=make_queue('b'*40)
    assert len(q['runs'])==6 and q['max_parallel']==1
    def inspect(value):
        if isinstance(value,dict):
            for key,item in value.items():
                if isinstance(key,str) and (key in ('approved','enabled','ready','stage_ready') or key.endswith('_ready')):
                    assert item is False
                inspect(item)
        elif isinstance(value,list):
            for item in value:inspect(item)
    inspect(q)
    assert {r['scene_version'] for r in q['runs']}=={'floor_light_v1','floor_light_textured_v1'}
    assert all(r['bundle']['weld'] is False for r in q['runs'])
    assert all(r['dependency_satisfied'] is False for r in q['runs'][3:])


def test_runner_records_scene_and_toggles_in_result_without_constructing_plant(tmp_path):
    b=run.bundle('c'*40,93550,1.,recovery_profile=g.PROFILE,revision_gate=rev.OPTION,
        multiframe_registration=reg.OPTION,render_profile='floor_light_textured_v1')
    def unavailable_backend(*a,**kw):
        raise RuntimeError('offline fake backend')
    result=run.acquire(tmp_path/'not-executed',b,unavailable_backend)
    assert result['status']=='HOST_ERROR' and result['frames']==0
    assert result['render_profile']=='floor_light_textured_v1'
    assert result['revision_gate']==rev.OPTION and not result['pool_with_previous_results']
