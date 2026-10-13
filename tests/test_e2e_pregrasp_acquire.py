import copy,json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from harness import e2e_pregrasp_acquire as m
from harness.e2e_carrier_approach import advance
from tests.test_e2e_align_progress import setup_transport


def test_uninitialized_station_scans_and_does_not_promote_old_beam():
    tr=setup_transport(pregrasp_acquire=m.OPTION,align_queues=m.QUEUES)
    r=tr.robots['r2'];r.last_beam=copy.deepcopy(r.beam);r.beam=None;r.goal.entities.pop('B')
    state={};out=m.acquire(tr,'r2',3.,state,None)
    assert not out[0] and 'station' not in state
    for now in (3.4,5.4,7.4,9.4,11.4):m.acquire(tr,'r2',now,state,None)
    assert len([e for e in tr.events if e['event']=='own_pregrasp_acquisition_view'])==5
    assert {e['camera'] for e in tr.events if e['event']=='own_pregrasp_acquisition_view'}=={'search','p45','inspect'}
    assert not r.beam and 'B' not in r.goal.entities and 'station' not in state
    m.acquire(tr,'r2',13.1,state,None)
    _,actions=m.acquire(tr,'r2',13.5,state,None)
    assert actions[0]['kind']=='mecanum' and actions[0].get('turn')


def test_recent_memory_only_seeds_a_hypothesis_fine_requires_current_rgb():
    tr=setup_transport(pregrasp_acquire=m.OPTION,pregrasp_recovery='bounded_search_v1')
    r=tr.robots['r1'];r.last_beam=copy.deepcopy(r.beam);r.beam=None
    fine,actions=advance(tr,'r1',4.)
    assert not fine and tr.approach['r1']['last_seen']==2.
    assert any(e['event']=='own_recent_beam_station_hypothesis' for e in tr.events)
    assert r.beam is None
    state={};m.acquire(tr,'r1',30.,state,r.goal.entities['B'])
    assert 'station' not in state


@pytest.mark.parametrize('mode,move',[('off',False),(m.QUEUES,True)])
def test_busy_alignment_robot_does_not_hold_its_peer_and_grasp_barrier_remains(monkeypatch,mode,move):
    from harness import e2e_carrier_approach
    tr=setup_transport(align_queues=mode);tr.set('align',0.)
    monkeypatch.setattr(e2e_carrier_approach,'advance',lambda *a:(False,[dict(kind='mecanum',forward=.35,left=0.,turn=0.,duration_s=.1)]))
    tr._poses('r1',0.,[({6:1600},.3,.6)])
    out=tr.step(.2)
    assert any(r=='r2' and a['kind']=='mecanum' for r,a in out)==move
    assert not any(r=='r1' and a['kind']=='mecanum' for r,a in out)
    tr.set('grasp_lift',.2)
    tr._open_epoch=lambda *a:pytest.fail('shared grasp queue barrier was skipped')
    tr.step(.4)


def test_off_leaves_uninitialized_search_unchanged():
    tr=setup_transport();r=tr.robots['r2'];r.beam=None;r.nav_command=dict(kind='hold')
    assert advance(tr,'r2',2.)==(False,[dict(kind='hold')]) and not tr.queue


def test_decode_once_preserves_recorded_result_and_removes_duplicate_jpeg_work(monkeypatch):
    import base64,cv2
    from harness.e2e_live_mapping import beam_observer
    data=Path('experiments/2026-10-12-e2e18/evidence/v231-s61010-r1-01070.jpg').read_bytes()
    image=base64.b64encode(data).decode();servo={1:2000,3:740,4:2320,5:1320,6:1047}
    real=cv2.imdecode;calls=[]
    def decode(*args):calls.append(1);return real(*args)
    monkeypatch.setattr(cv2,'imdecode',decode)
    old=beam_observer('long_side_v1')(image,servo);before=len(calls);calls.clear()
    new=beam_observer('long_side_v1','once_v1')(image,servo)
    assert old==new and before==2 and len(calls)==1


def test_v235_bundle_registration():
    from scripts.run_e2e_ownmap_live import bundle
    from tests.test_e2e18 import options,ROOT
    from harness.e2e_runtime_registration import require_current
    kw=dict(speed5='lean_v3',observation_cadence='on_v1',route_guard='dev_nominal_v1',beam_axis='undirected_v1',route_coverage='native_v1',carrier_axes='beam_v1',carrier_approach='standoff_v1',route_extent='goal_envelope_v1',record_scalars='python_v1',pose_guard='se2_innovation_v1',protocol_recovery='envelope_retry_v1',camera_load='nominal_command_v1',route_tokens='1600_v1',protocol_progress='stage_retry_v1',route_cost='bounded_morphology_v1',align_progress='dev_continue_v1',pregrasp_recovery='bounded_search_v1',pregrasp_gaze='own_bearing_v1',search_bearing='last_seen_v1',pulse_admission='finish_active_v1',event_projection='route_hash_v1',pregrasp_progress='backup_replan_v1',gaze_cadence='settled_frames_v1',stage_physics='pregrasp_dt1_v1',protocol_idempotency='same_route_v1',route_handle="typed_ref_v1",boundary_frame="observed_own_v1",beam_end_model="long_side_v1",beam_avoidance="own_obstacle_v1",pregrasp_acquire=m.OPTION,align_queues=m.QUEUES,beam_decode="once_v1",mapping_acquire=m.MAPPING)
    b=bundle('a'*40,61002,'study_gemma4_31b_v1',**options(),**kw);require_current(b,ROOT)
    assert b['execution_bundle_id']=='e2e18-v235'
    assert 'harness/e2e_pregrasp_acquire.py' in b['source_sha256']
    b['e2e_options']['pregrasp_acquire']='off'
    with pytest.raises(ValueError):require_current(b,ROOT)


def test_mapping_scan_is_bounded_and_keeps_peer_navigation():
    tr=setup_transport(pregrasp_acquire=m.OPTION,align_queues=m.QUEUES)
    tr.mapping_acquire=m.MAPPING;tr.mapping_acquisitions={}
    for rid,r in tr.robots.items():
        r.packet=None;r.nav_command=dict(kind='mecanum',forward=.35,left=0.,turn=0.,duration_s=.1)
        r.goal.e2e_gate=SimpleNamespace(references={'B':{'ref':{'t_sim':1.,'frame_id':1}}})
    r=tr.robots['r1'];r.beam=None
    first=m.mapping_commands(tr,10.);assert all(a['kind']=='mecanum' for _,a in first)
    scan=m.mapping_commands(tr,17.)
    assert ('r2',tr.robots['r2'].nav_command) in scan
    assert next(a for rid,a in scan if rid=='r1')['kind']=='hold'
    m.mapping_commands(tr,17.4);assert tr.queue
    r.beam={'fresh':True}
    assert next(a for rid,a in m.mapping_commands(tr,18.) if rid=='r1')['kind']=='hold'
    r.beam=None;tr._drain(30.)
    resumed=m.mapping_commands(tr,30.)
    assert next(a for rid,a in resumed if rid=='r1')==r.nav_command
    assert tr.mapping_acquisitions['r1']['next']==60.
    tr.mapping_acquire='off';assert m.mapping_commands(tr,50.)==[(rid,r.nav_command) for rid,r in tr.robots.items()]
