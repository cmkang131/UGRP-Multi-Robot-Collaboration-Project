"""Offline stage boundary tests: no simulator construction, renders or network."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from harness import e2e_stage_checkpoint as cp
from scripts.run_e2e_stage_probe import commands_for_stage, stage_bundle, stage_metrics, run
from sim.e2e_stage_staging import HeldWindow


def fixture(tmp_path):
    raw=tmp_path/'case'/'raw';raw.mkdir(parents=True)
    def put(name,value,lines=False):
        p=raw/name;p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text('\n'.join(json.dumps(r) for r in value) if lines else json.dumps(value))
    put('bundle.json',dict(execution_bundle_id='e2e18-v375',e2e_options={}))
    put('scene.json',dict(scene='static'))
    put('transport-trace.json',[dict(t=2.,event='phase',state='align')])
    put('eval_only/referee_truth.jsonl',[dict(t=t,items=dict(beam_1=dict(x=1,y=2,z=.016,yaw=0))) for t in (1.3,3.3,4.3)],True)
    for rid in cp.ROBOTS:
        put(f'eval_only/{rid}/trajectory.jsonl',[dict(t=t,robot_xyz_m=[0,0,.1],robot_yaw_rad=0) for t in (1.3,3.3,4.3)],True)
        put(f'robots/{rid}/commands.jsonl',[dict(t=1.3,kind='initial_servo_command',pulses={'1':2000}),
            dict(t=2.3,kind='hold'),dict(t=3.3,kind='look',pan_pulse=1700),dict(t=4.3,kind='hold')],True)
        put(f'robots/{rid}/frames.jsonl',[dict(frame_id=i+1,sim_time=t+1.3,sha256=str(i),path=f'robots/{rid}/rgb/{i}.jpg') for i,t in enumerate((0,2,3))],True)
        put(f'robots/{rid}/ownmap.jsonl',[dict(t=t,frame_id=i+1,sha256=str(i),pose_own_m=[t,0,0],remembered_B=None,own_beam=None) for i,t in enumerate((0,2,3))],True)
    return raw


def test_prepare_selects_causal_prefix_and_clock(tmp_path):
    c=cp.prepare(fixture(tmp_path));cp.verify_recipe(c)
    assert c['cutoff_s']==2 and c['source_origin_s']==1.3
    for own in c['own_inputs'].values():
        assert [r['t'] for r in own['frames']]==[0,2]
        assert [r['t'] for r in own['commands']]==[0,1]
        assert 'actuator_state' not in str(own)
    assert c['setup_only']['controller_feedback'] is False
    assert c['setup_only']['robots']['r1']['t']==3.3
    assert not c['historical_grid_hash_available']


def test_mapping_cutoff_and_no_future_gt(tmp_path):
    raw=fixture(tmp_path)
    c=cp.prepare(raw,stage='mapping',cutoff=0)
    assert len(c['own_inputs']['r1']['frames'])==1
    assert c['setup_only']['robots']['r1']['t']==1.3
    with pytest.raises(ValueError,match='CUTOFF'):cp.prepare(raw,stage='mapping',cutoff=2)
    with pytest.raises(ValueError,match='CUTOFF'):cp.prepare(raw,stage='align',cutoff=1)


def test_hash_rejects_modified_setup_or_own_inputs(tmp_path):
    c=cp.prepare(fixture(tmp_path));c['setup_only']['beam']['x']=999
    with pytest.raises(ValueError,match='HASH'):cp.verify_recipe(c)


def test_missing_truth_does_not_use_future():
    with pytest.raises(ValueError,match='MISSING'):cp.at_or_before([{'t':2}],1)
    with pytest.raises(ValueError,match='STALE'):cp.at_or_before([{'t':0}],2)


def test_range_correction_is_not_silently_dropped(tmp_path):
    raw=fixture(tmp_path);p=raw/'robots/r1/ownmap.jsonl';rs=cp.rows(p)
    rs[0]['stall_odometry']={'counts':{'us_zero':1}}
    p.write_text('\n'.join(map(json.dumps,rs)))
    with pytest.raises(ValueError,match='RANGE_CORRECTION'):cp.prepare(raw)


def test_no_protocol_or_carry_execution_after_alignment():
    calls=[]
    tr=SimpleNamespace(state='grasp_lift',step=lambda t:pytest.fail('carry/protocol step called'),_drain=lambda t:calls.append(t) or [])
    assert commands_for_stage(tr,2)==[] and calls==[2]
    tr.state='carry'
    with pytest.raises(ValueError,match='ESCAPE'):commands_for_stage(tr,3)


def test_both_held_requires_simultaneous_sustained_bilateral_contact():
    h=HeldWindow()
    assert not h.sample(0,dict(r1=True,r2=False))
    assert not h.sample(.3,dict(r1=True,r2=True))
    assert not h.sample(.4,dict(r1=False,r2=True))
    assert not h.sample(.6,dict(r1=True,r2=True))
    assert h.sample(.9,dict(r1=True,r2=True))
    assert h.first==dict(r1=.3,r2=.6)


def test_all_conditions_keep_same_baseline_except_candidate():
    base=dict(execution_bundle_id='e2e18-v375',e2e_options=dict(body_controller='off',stale_station='expire12_v1'))
    before=copy.deepcopy(base)
    for condition,mode in [('v375','off'),('v384','regulated_v1'),('v385','gaze_v1'),('v386','track_gaze_v1')]:
        b=stage_bundle({'checkpoint_sha256':'fixed'},base,condition,62001,'sha')
        assert b['e2e_options']==dict(base['e2e_options'],grasp_once=mode)
        assert b['parent_controller']=='e2e18-'+condition
        assert b['case_cap_s']==300 and not b['E2E_success_eligible']
    assert base==before


def test_metrics_do_not_turn_timeout_into_success():
    events=[dict(event='own_pregrasp_acquisition_begin',robot_id='r2')]
    r=stage_metrics(events,{},False,300)
    assert not r['first_attempt_success'] and r['both_held_s'] is None
    assert r['censored_s']==300 and r['reacquisition_entries']==dict(r1=0,r2=1)
    assert not stage_metrics(events,dict(r1=2,r2=4),True,4)['first_attempt_success']
    assert stage_metrics([],dict(r1=2,r2=4),True,4)['held_gap_s']==2


def test_toggle_off_precedes_physics():
    with pytest.raises(ValueError,match='TOGGLE_OFF'):run(SimpleNamespace(enable_stage=False))


def test_mac_run_is_blocked(monkeypatch):
    monkeypatch.setattr('scripts.run_e2e_stage_probe.platform.system',lambda:'Darwin')
    with pytest.raises(ValueError,match='NO_MAC'):run(SimpleNamespace(enable_stage=True))


def test_replay_supplies_only_own_prefix_and_refuses_bad_jpeg(tmp_path,monkeypatch):
    import hashlib
    import io
    import numpy as np
    from PIL import Image
    raw=fixture(tmp_path);c=cp.prepare(raw)
    buf=io.BytesIO();Image.new('RGB',(2,2)).save(buf,format='JPEG');jpeg=buf.getvalue()
    for own in c['own_inputs'].values():
        for f in own['frames']:
            f['sha256']=hashlib.sha256(jpeg).hexdigest();f['expected_pose']=[0,0,0]
            p=raw/f['path'];p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(jpeg)
    c['checkpoint_sha256']=cp.digest({k:v for k,v in c.items() if k!='checkpoint_sha256'})
    seen=[]
    def factory(b):
        result={}
        for rid in cp.ROBOTS:
            def receive(obs,rgb,rid=rid):
                assert set(obs)=={'frame_id','sim_time','sha256','image'}
                seen.append((rid,obs['sim_time']))
            result[rid]=SimpleNamespace(goal=SimpleNamespace(explorer=SimpleNamespace(local_pose=np.zeros(3)),entities={}),
                servo={},beam=None,receive=receive,commanded=lambda a,t:None)
        return result
    monkeypatch.setattr('harness.e2e_observation_cadence.configure',lambda *a:None)
    monkeypatch.setattr(cp,'own_map_record',lambda r:dict(pose=r.goal.explorer.local_pose.tolist()))
    _,receipt=cp.replay(c,raw,robot_factory=factory)
    assert len(seen)==6 and max(t for r,t in seen)==2
    assert all(r['map_sha256']==r['roundtrip_sha256'] for r in receipt.values())
    (raw/c['own_inputs']['r1']['frames'][0]['path']).write_bytes(b'corrupted')
    with pytest.raises(ValueError,match='RGB_HASH'):cp.replay(c,raw,robot_factory=factory)


def test_summary_denominators_and_paired_identity():
    from scripts.summarize_e2e_stage_probe import summarize
    matrix=dict(conditions=['v375','v384'],source_runs=['case'],core_source_runs=['case'],seeds=[1],
        runs=[dict(source_run='case',seed=1,condition=c,checkpoint_sha256='fixed') for c in ('v375','v384')])
    a=dict(source_run='case',seed=1,condition='v375',checkpoint_sha256='fixed',status='SIM_BUDGET_EXHAUSTED',both_held=False,first_attempt_success=False)
    b=dict(a,condition='v384',status='BOTH_HELD',both_held=True,first_attempt_success=True,both_held_s=23)
    pending=summarize(matrix,[a]);assert pending['all']['observed_N']==1 and pending['all']['missing_N']==1
    s=summarize(matrix,[a,b]);assert s['all']['first_attempt_n']==1 and s['core']['planned_N']==2
    assert s['paired']['v384']['paired_N']==1 and s['paired']['v384']['both_completed_delta_s']['n']==0
    with pytest.raises(ValueError,match='DUPLICATE'):summarize(matrix,[a,a])
    with pytest.raises(ValueError,match='CHECKPOINT'):summarize(matrix,[dict(a,checkpoint_sha256='wrong')])


def test_registered_workflow_is_plan_only(tmp_path):
    from sim.workflow_manager import plan
    root=Path(__file__).resolve().parents[1]
    source=tmp_path/'fixture.json';source.write_text('{}')
    p=plan(root,'e2e18-v387',['run','--enable-stage','--checkpoint',str(source),'--raw',str(tmp_path),
        '--baseline-bundle',str(source),'--condition','v375','--seed','62001','--expected-source-sha','0'*40,'--batch','test'])
    assert p['execution_started'] is False
    assert p['runner']=='scripts.run_e2e_stage_probe'
    assert p['command'][3:5]==['run','--enable-stage']


@pytest.mark.parametrize('cap,wall',[(301,1800),(.051,1800),(300,float('inf')),(300,1801)])
def test_finite_short_budget_before_backend(monkeypatch,cap,wall):
    monkeypatch.setattr('scripts.run_e2e_stage_probe.platform.system',lambda:'Linux')
    with pytest.raises(ValueError,match='CAP'):run(SimpleNamespace(enable_stage=True,cap_s=cap,wall_cap_s=wall))


def test_changed_scene_or_camera_model_is_rejected():
    from sim.e2e_stage_staging import verify_scene
    original=dict(static_map_sha256='map1',robot_xml_sha256={'r1':'camera1'})
    verify_scene(original,original)
    with pytest.raises(ValueError,match='FINGERPRINT'):verify_scene(dict(original,static_map_sha256='map2'),original)
    with pytest.raises(ValueError,match='FINGERPRINT'):verify_scene(dict(original,robot_xml_sha256={'r1':'camera2'}),original)


def test_time_delta_requires_same_reconstructed_map_and_physics():
    from scripts.summarize_e2e_stage_probe import summarize
    matrix=dict(conditions=['v375','v384'],source_runs=['case'],core_source_runs=[],seeds=[1],
        runs=[dict(source_run='case',seed=1,condition=c,checkpoint_sha256='fixed') for c in ('v375','v384')])
    a=dict(source_run='case',seed=1,condition='v375',checkpoint_sha256='fixed',status='BOTH_HELD',both_held=True,both_held_s=30,
        own_map_sha256={'r1':'map'},initial_physics_sha256='pose',source_sha='source')
    b=dict(a,condition='v384',both_held_s=20,own_map_sha256={'r1':'different'})
    s=summarize(matrix,[a,b])['paired']['v384'];assert s['verified_same_state_N']==0 and s['both_completed_delta_s']['n']==0
    b['own_map_sha256']=a['own_map_sha256']
    s=summarize(matrix,[a,b])['paired']['v384'];assert s['verified_same_state_N']==1 and s['both_completed_delta_s']['median']==-10


def test_replay_hash_matches_source_numpy_scalar_writer():
    import numpy as np
    from harness.e2e_record_scalars import normalize
    value=dict(observation=dict(confirmed=np.bool_(True),node=np.int64(4),area=np.float32(.25)))
    assert cp.digest(value)==cp.digest(normalize(value))


def test_source_policy_handoff_keeps_map_and_recovery_history():
    from harness.e2e_stage_policy import install
    robots={rid:SimpleNamespace(body_controller='jev_v1',decider='off',
        goal=SimpleNamespace(explore_deadlock=SimpleNamespace(idle_threshold_s=30.,idle_since=127.4,cycles=0),
                             explorer=SimpleNamespace(grid=object()))) for rid in cp.ROBOTS}
    grids={rid:r.goal.explorer.grid for rid,r in robots.items()}
    assert not install(robots,{},dict(explore_idle='idle5_v1'))['applied']
    assert robots['r2'].goal.explore_deadlock.idle_threshold_s==30
    receipt=install(robots,dict(body_controller='jev_v1'),dict(explore_idle='idle5_v1'),'baseline_v1')
    assert receipt['before']['r2']['idle_s']==30 and receipt['after']['r2']['idle_s']==5
    assert all(r.goal.explorer.grid is grids[rid] for rid,r in robots.items())
    assert robots['r2'].goal.explore_deadlock.idle_since==127.4
    assert robots['r2'].body_controller=='off'
    with pytest.raises(ValueError,match='STATE_MIGRATION'):
        install(robots,dict(pose_fix='old'),dict(pose_fix='new'),'baseline_v1')
