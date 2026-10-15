"""Known-mode tracking, retained global recovery, budget and v7 boundaries."""
import json
import math
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from harness.reloc14_tracking import track


def registration():
    return SimpleNamespace(map_from_own=np.zeros(3),command_registration_anchor=np.zeros(3),
        geometry_supported=lambda *a:(True,{'independent_line_axes':True}),
        pf=SimpleNamespace(landmark_map=SimpleNamespace(edges=[])),
        confirmations=[np.zeros(3)]*3,confirmation_views={1,2,3},
        execution_r7_admitted=True,tracking_state='TRACKING')


def row(updated=True):
    return dict(pose=[.02,0,.01],covariance=np.diag([.01**2,.01**2,.01**2]).tolist(),
        updated=updated,resolved=True,cluster={'mass':1.},sensor=None)


def test_tracking_measurement_and_motion_gate_do_not_repeat_global_views(monkeypatch):
    from harness.selfmap5_registration import MultiFrameEvidence
    monkeypatch.setattr(MultiFrameEvidence,"supported",lambda *a:(False,dict(supported_floor_lines=1)))
    r=registration()
    fix,handled=track(r,row(),{'features':[]},np.zeros(3),1.)
    assert handled and r.last['tracking']['measurement']
    assert not r.last['tracking']['global_confirmations_required']
    assert len(r.confirmation_views)==3
    track(r,row(False),{'features':[]},np.zeros(3),2.)
    assert r.execution_r7_admitted and not r.last['tracking']['measurement']


def test_fresh_tracking_failure_loses_mode_stale_frame_does_not(monkeypatch):
    from harness.selfmap5_registration import MultiFrameEvidence
    monkeypatch.setattr(MultiFrameEvidence,"supported",lambda *a:(False,dict(supported_floor_lines=0)))
    r=registration();r.geometry_supported=lambda *a:(False,{})
    assert track(r,row(False),{'features':[]},np.zeros(3),1.)[1]
    assert not track(r,row(True),{'features':[]},np.zeros(3),2.)[1]
    assert r.tracking_state=='LOST' and not r.execution_r7_admitted
    assert not r.confirmations and not r.confirmation_views
    assert r.last_tracking_failure['category']=='tracking_evidence_lost'


def test_prior_seeded_orb_cannot_take_over_pf_tracking(monkeypatch):
    from harness.selfmap6_safety import GatedPriorSLAM
    s=GatedPriorSLAM('r1',max_sigma_xy_m=.15,max_sigma_yaw_rad=math.radians(5))
    s.reloc14_pf_tracking=True
    p,_,d=s._fit(np.empty((0,2)),np.empty((0,32)),np.zeros(3),1)
    assert p is None and d['reason']=='pf_tracking_or_relocalization'


def test_refitted_carry_envelope_retains_partial_epoch_and_existing_task_limit():
    from sim.solo_carry_pose import CommandPose,task_start
    c=CommandPose(task_start({'regions':{'pickup':{'center_m':[0,0],'half_extents_m':[.5,.5]}}}),
        drive_model_deadband_v1=True,reloc10_rotation_calibration_v1=True,reloc14_carry_budget_v1=True)
    c.turn_since_fix=2.
    assert c.sigmas()[2]>math.radians(20) and not c.ready(0.)
    c.partial_epoch=(0.,1.)
    assert c.sigmas()[2]==pytest.approx(math.radians(4.522386263900104+20.584161983501907))
    assert c.yaw_budget_limit()==pytest.approx(math.radians(20))


def test_v7_scene_source_and_carry_plan_keep_crate_out():
    from harness.zone_environment_registry import load_scenario
    root=Path(__file__).resolve().parents[1]
    manifest=json.loads((root/'experiments/2026-10-15-reloc14/v7-scenario-source.json').read_text())
    import hashlib
    for name,sha in manifest['sha256'].items():
        assert hashlib.sha256((root/name).read_bytes()).hexdigest()==sha
        s=load_scenario(Path(name).stem)
        assert all(p['kind']!='heavy_crate' for p in s['eval']['setup']['placements'])


def test_tracking_option_requires_global_safety_chain():
    from harness.self_map_integration import Options
    with pytest.raises(ValueError):Options(reloc14_continuous_tracking_v1=True)


def test_carry_pf_initializes_from_declared_prior_and_consumes_only_issued_delta(monkeypatch):
    from harness.selfmap4_geometry import static_input
    from sim.solo_carry_pose import task_start
    from sim.reloc14_carry_tracking import CarryTracker
    static,_=static_input();start=task_start(static);c=CarryTracker(static,start)
    np.testing.assert_allclose(c.pf.px.mean(0),start['pose_m_rad'],atol=.01)
    called=[]
    def step(**kw):
        called.append(kw);return dict(row(False),updates=0)
    monkeypatch.setattr(c.pf,'step',step)
    c.issue(dict(t=0.,pwm={1:2000,3:900,4:2400,5:1320,6:1500}),[.02,0,.01])
    assert c.observe(np.zeros((480,640,3),np.uint8),.1) is None
    np.testing.assert_allclose(called[-1]['delta'],[.02,0,.01])
    np.testing.assert_allclose(c.pending,0.)


def test_compute_budget_uses_graph_size_and_preserves_existing_path():
    from harness.own_map_navigation import astar
    clear=np.ones((20,20),bool);clear[3:17,10]=False
    assert astar(clear,(1,1),(18,18),compute_budget_v1=True)==astar(clear,(1,1),(18,18))


def test_known_mode_wall_only_update_is_partial_tracking(monkeypatch):
    from harness.selfmap5_registration import MultiFrameEvidence
    monkeypatch.setattr(MultiFrameEvidence,'supported',lambda *a:(False,dict(supported_floor_lines=0)))
    r=registration();r.pf.field=SimpleNamespace(distances=lambda p:np.zeros(len(p)))
    result,handled=track(r,row(),dict(features=[],segments=[[[0.,1.],[1.,1.]]]),np.zeros(3),1.)
    assert handled and result is not None and r.execution_r7_admitted
    assert r.last['geometry']['supported_wall_field_points']>0


def test_carry_closed_gripper_retains_prediction_without_unqualified_fk(monkeypatch):
    from harness import selfmap4_geometry as g
    from sim.solo_carry_pose import task_start
    from sim.reloc14_carry_tracking import CarryTracker
    static,_=g.static_input();c=CarryTracker(static,task_start(static))
    c.issue(dict(t=0.,pwm={1:1200,3:900,4:2400,5:1320,6:1500}),[0,0,0])
    monkeypatch.setattr(g,'observe',lambda *a,**kw:pytest.fail('unqualified loaded camera transform'))
    monkeypatch.setattr(c.pf,'step',lambda **kw:dict(row(False),updates=0))
    assert c.observe(np.zeros((480,640,3),np.uint8),3.) is None
    assert c.last['camera_admission']=='loaded_or_unknown_prediction_only'


def test_existing_carry_bgr_port_converts_to_rgb_once():
    from sim.solo_carry_pose import CommandPose,task_start
    c=CommandPose(task_start({'regions':{'pickup':{'center_m':[0,0],'half_extents_m':[.5,.5]}}}))
    captured=[];c.tracker=SimpleNamespace(observe=lambda rgb,t:captured.append(rgb))
    bgr=np.zeros((480,640,3),np.uint8);bgr[0,0]=[255,0,0]
    c.observe_own(bgr,0.,camera='r1/robot_cam')
    assert captured[0][0,0].tolist()==[0,0,255]


def test_queue_requires_real_table_and_keeps_blocked_runs_disabled(tmp_path):
    from scripts.prepare_reloc14_queues import queues
    with pytest.raises(ValueError,match='REJECTION_TABLE_REQUIRED'):
        queues('a'*40,tmp_path,tmp_path/'missing',[],[])
    table=tmp_path/'funnel.json';table.write_text('{}')
    qs=queues('a'*40,tmp_path,table,[],[])
    assert [q['run_count'] for q in qs]==[8,11]
    for q in qs:
        assert q['max_parallel']==16 and q['status']=='BLOCKED'
        assert q['rejection_table']==str(table)
        assert all(r['source_sha']=='a'*40 and not r['execute'] and not r['approved'] for r in q['runs'])
    assert qs[1]['runs'][0]['seed']==93266 and qs[1]['runs'][1]['seed']==93315
    assert all('--execute' in r['command'] for r in qs[0]['runs'])
    assert all('--execute' not in r['command'] for r in qs[1]['runs'])


def test_supported_uncertain_tracking_retains_mode_and_full_covariance(monkeypatch):
    from harness.selfmap5_registration import MultiFrameEvidence
    monkeypatch.setattr(MultiFrameEvidence,'supported',lambda *a:(False,dict(supported_floor_lines=1)))
    r=registration();measurement=row();measurement['resolved']=False
    measurement['covariance']=np.diag([.04**2,.04**2,math.radians(5.02)**2]).tolist()
    result,handled=track(r,measurement,dict(features=[],segments=[]),np.zeros(3),1.)
    assert handled and r.tracking_state=='TRACKING' and r.execution_r7_admitted
    assert not r.last['resolved'] and not r.last['tracking']['precision_admitted']
    assert result[1][2,2]>math.radians(5)**2  # unchanged map/drive uncertainty gate sees it


def test_saved_93585_short_pulse_is_filtered_before_native_output():
    from harness.active_wall_mapping import pulse_command
    from harness.self_pulse_rotation import OPTION
    request=np.array([.037779776768443775,0.,0.])
    legacy,_=pulse_command(request,41.5,motion_model=OPTION,translation_policy='forward_only_v1')
    assert legacy['duration_s']==.06  # actual failing R3 calibrated response
    fixed,receipt=pulse_command(request,41.5,motion_model=OPTION,translation_policy='forward_only_v1',native_primitives=True)
    assert fixed['kind']=='hold' or fixed['duration_s']>=.10
    assert receipt['native_profile_rejections']


def test_native_turn_settler_uses_only_the_same_supported_lattice():
    from harness.reloc10_settle import settle_turn,turn_quantum
    from harness.self_pulse_rotation import OPTION
    from sim.settle_pulse import PulseSettler
    assert turn_quantum(OPTION,native_primitives=True)>=turn_quantum(OPTION)
    c,r=settle_turn(PulseSettler(math.radians(2)),.2,0.,costmap=SimpleNamespace(pose_clear=lambda p:True),
        pose=np.zeros(3),motion_model=OPTION,native_primitives=True)
    assert c['kind']=='hold' or c['duration_s']>=.10
