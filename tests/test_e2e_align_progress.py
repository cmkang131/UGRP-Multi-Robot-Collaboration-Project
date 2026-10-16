import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from harness.e2e_live_transport import Transport
from harness.e2e_carrier_approach import advance
from harness.owncam_pair_beam_v2 import pose_of
from tests.test_e2e18_route_guard import goal


def setup_transport(**opts):
    profiles=json.loads(Path('configs/s2_v133_full_template.json').read_text())['pulse_calibration']['profiles']
    robots={}
    for rid in ('r1','r2'):
        g=goal();g.explorer.local_pose=np.array([-1.,0.,0.]);g.explorer.latest={}
        g.explorer.navigator=SimpleNamespace(plan_to=lambda cm,pose,target:[])
        b=dict(rgb=dict(frame_id=10,t_sim=2.),pose_own_m=[0.,0.,0.],grip_base_m=[.73,0.],axis_heading_rad=0.)
        robots[rid]=SimpleNamespace(goal=g,beam=b,last_obs={'frame_id':10},servo=pose_of('search'),nav_command={'kind':'hold'})
    return Transport(robots,None,profiles,carrier_approach='standoff_v1',**opts)


@pytest.mark.parametrize('dev,option,expected',[(True,'dev_continue_v1','mecanum'),(True,'off',None),(False,'dev_continue_v1','hold')])
def test_actual_align_preserves_dev_commands_after_timeout(monkeypatch,dev,option,expected):
    import harness.e2e_carrier_approach as approach
    monkeypatch.setattr(approach,'advance',lambda *a:(False,[dict(kind='mecanum',forward=20,duration_s=.1)]))
    tr=setup_transport(dev_light=dev,align_progress=option);tr.set('align',0.)
    out=tr._align(80.)
    assert ([v['kind'] for _,v in out] if expected else out)==([expected]*2 if expected else [])
    if dev:assert [v['event'] for v in tr.events].count('would_stop')==1
    else:assert tr.failure=='OWN_RGB_ALIGNMENT_TIMEOUT'


def test_stale_beam_search_has_only_commanded_camera_motion_and_fresh_cancels():
    tr=setup_transport(dev_light=True,pregrasp_recovery='bounded_search_v1');r=tr.robots['r1']
    advance(tr,'r1',2.);tr.queue.clear()
    for i,t in enumerate((5.,6.3,7.5,8.7)):
        r.last_obs['frame_id']=11+i
        fine,actions=advance(tr,'r1',t)
        assert not fine and actions==[{'kind':'hold'}]
        assert r.carrier_approach['status']=='reacquire_own_beam'
    assert tr.queue and all(a['kind'] in ('arm','look') for _,_,a in tr.queue)
    assert {e['camera'] for e in tr.events if e['event']=='own_beam_search_view'} >= {'search','p45','inspect'}
    r.last_obs['frame_id']=20;r.beam['rgb']['t_sim']=9.
    advance(tr,'r1',9.)
    assert 'search_started' not in tr.approach['r1']


@pytest.mark.parametrize('dev,recovery,expected',[(True,'bounded_search_v1','mecanum'),(True,'off','hold'),(False,'bounded_search_v1','hold')])
def test_fresh_visual_station_no_path_is_only_bypassed_in_dev(dev,recovery,expected):
    tr=setup_transport(dev_light=dev,pregrasp_recovery=recovery)
    fine,actions=advance(tr,'r1',2.)
    assert not fine and actions[0]['kind']==expected
    assert bool([e for e in tr.events if e['event']=='would_stop_pregrasp_no_path'])==(expected=='mecanum')


def test_v229_bundle_runtime_registration_and_defaults():
    from scripts.run_e2e_ownmap_live import bundle
    from tests.test_e2e18 import options,ROOT
    from harness.e2e_runtime_registration import require_current
    args=dict(speed5='lean_v3',observation_cadence='on_v1',route_guard='dev_nominal_v1',beam_axis='undirected_v1',route_coverage='native_v1',carrier_axes='beam_v1',carrier_approach='standoff_v1',route_extent='goal_envelope_v1',record_scalars='python_v1',pose_guard='se2_innovation_v1',protocol_recovery='envelope_retry_v1',camera_load='nominal_command_v1',route_tokens='1600_v1',protocol_progress='stage_retry_v1',route_cost='bounded_morphology_v1')
    old=bundle('a'*40,61003,'study_gemma4_31b_v1',**options(),**args)
    assert old['execution_bundle_id']=='e2e18-v228'
    b=bundle('a'*40,61003,'study_gemma4_31b_v1',**options(),**args,align_progress='dev_continue_v1',pregrasp_recovery='bounded_search_v1')
    require_current(b,ROOT);assert b['execution_bundle_id']=='e2e18-v229'
    assert 'harness/e2e_align_progress.py' in b['source_sha256']
    b['e2e_options']['pregrasp_recovery']='off'
    with pytest.raises(ValueError):require_current(b,ROOT)
