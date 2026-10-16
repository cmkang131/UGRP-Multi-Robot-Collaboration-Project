"""Own-input/communication/error/admission regressions. No physics or render."""
import io
import json
from pathlib import Path
from urllib.error import URLError

import pytest

from harness.e2e_warp_runtime import (OwnFrame, Channels, Planner, ConnectionHealth,
                                     rejection, first30)
from harness.e2e_warp_components import require_components
from harness.zone_study_contract import ContractViolation


def frame(robot='r1', world=0):
    return OwnFrame(robot, world, 0, 0., b'own-image', ())


def test_cross_robot_world_image_never_enters_prompt(tmp_path):
    p = Planner('http://127.0.0.1:1', tmp_path/'r1', {}, run_id='e2ewarp-test', world_id=0, robot='r1')
    for f in (frame('r2'), frame(world=1)):
        with pytest.raises(ValueError, match='cross robot/world'):
            p.body(f, {})
    body = p.body(frame(), {'sim_s': 0})
    assert [m['role'] for m in body['messages']] == ['system', 'user', 'user']
    assert body['messages'][1]['content'] == '{}'
    assert [v['type'] for v in body['messages'][-1]['content']] == ['text', 'image_url']


def test_no_comm_has_no_inbox_and_rejects_message():
    channel = Channels('no_comm', 601)
    assert channel.inbox('r1') == {}
    with pytest.raises(ContractViolation):
        channel.send('r1', {'recipients': ['r2'], 'body': {'text': '기다려'}}, now=0)


def test_leader_star_and_world_isolation():
    a, b = Channels('leader_ko', 601), Channels('leader_ko', 601)
    assert a.leader == 'r2'
    with pytest.raises(ContractViolation):
        a.send('r1', {'recipients': ['r3'], 'body': {'text': '기다려'}}, now=0)
    a.send('r1', {'recipients': ['r2'], 'body': {'text': '기다려'}}, now=0)
    assert len(a.inbox('r2')['inbox']) == 1
    assert b.inbox('r2')['inbox'] == []
    assert a.inbox('r2')['inbox'] == []


def test_structured_has_no_free_text_side_channel():
    c = Channels('structured', 601)
    with pytest.raises(ContractViolation):
        c.send('r1', {'recipients': ['r2'], 'body': {'text': '기다려'}}, now=0)
    c.send('r1', {'recipients': ['r2'], 'body': {'act': 'inform', 'state': 'unknown'}}, now=0)
    assert c.inbox('r2')['inbox'][0]['body'] == {'act': 'inform', 'state': 'unknown'}
    c.send('r1', {'recipients': ['r2','r3'], 'body': {'act': 'inform', 'state': 'unknown'}}, now=1)
    received=c.inbox('r2')['inbox'][0];received['body']['state']='held'
    assert c.inbox('r3')['inbox'][0]['body']['state']=='unknown'
    assert c.events[-1]['body']['state']=='unknown'


@pytest.mark.parametrize('times', [(0, 1, 2), (0, 30.1)])
def test_connection_loss_is_host_error(times):
    h = ConnectionHealth()
    for t in times[:-1]:
        h.observe(False, t)
    with pytest.raises(RuntimeError, match='HOST_ERROR:LLM_CONNECTION_LOST'):
        h.observe(False, times[-1])


class Reply(io.BytesIO):
    status = 200


def complete(finish='stop', provider='CoreWeave'):
    return Reply(json.dumps(dict(provider=provider, choices=[dict(finish_reason=finish,
        message=dict(content=json.dumps({'act': 'wait', 'message': None})))],
        usage=dict(prompt_tokens=100, total_tokens=105, prompt_tokens_details={'cached_tokens': 50}),
        ugrp_openrouter=dict(attempts=[dict(attempt=1,status=200)]))).encode())


@pytest.mark.parametrize('finish,provider', [('length', 'CoreWeave'), ('stop', 'DeepInfra')])
def test_paid_abnormal_reply_has_usage_but_executes_nothing(tmp_path, finish, provider):
    p = Planner('http://127.0.0.1:1', tmp_path/'r1', {}, run_id='e2ewarp-test', world_id=0, robot='r1',
                http_open=lambda *a, **k: complete(finish, provider))
    answer, reason = p.decide(frame(), {'candidates': [{'id': 'wait'}]})
    assert answer is None and reason['reason']
    assert p.rows[0]['usage']['total_tokens'] == 105
    assert not p.rows[0]['accepted']
    request = json.loads((tmp_path/'r1/00001.request.json').read_text())
    assert request['messages'][-1]['content'][-1]['image_url']['removed']
    assert 'b3duLWltYWdl' not in json.dumps(request)


def test_actual_model_choice_and_usage(tmp_path):
    p = Planner('http://127.0.0.1:1', tmp_path/'r1', {}, run_id='e2ewarp-test', world_id=0, robot='r1',
                http_open=lambda *a, **k: complete())
    answer, reason = p.decide(frame(), {'candidates': [{'id': 'wait'}]})
    assert answer == {'act': 'wait', 'message': None} and reason is None
    r = first30(p.rows, [answer], 30., 1, 15.)
    assert r['model_calls'] == 1 and r['cache_ratio'] == .5
    assert r['tokens_per_sim_s'] == 3.5 and not r['E2E_success']


def test_real_transport_disconnect_stops_third_call(tmp_path):
    def fail(*a, **k):
        raise URLError('disconnected')
    p = Planner('http://127.0.0.1:1', tmp_path/'r1', {}, run_id='e2ewarp-test', world_id=0, robot='r1', http_open=fail)
    p.decide(frame(), {'candidates': []})
    p.decide(frame(), {'candidates': []})
    with pytest.raises(RuntimeError, match='HOST_ERROR'):
        p.decide(frame(), {'candidates': []})
    assert len(p.rows) == 3


def test_missing_components_never_load_physics_or_old_actor(tmp_path):
    with pytest.raises(ValueError, match='DEPENDENCY_WAIT'):
        require_components(None, tmp_path)
    p = tmp_path/'components.json'
    p.write_text('{}')
    with pytest.raises(ValueError, match='navigation'):
        require_components(p, tmp_path)


def test_rejection_never_has_blank_reason_or_fabricated_gap():
    r = rejection('static_map_unregistered')
    assert r['blocked_object'] == 'not_observed' and r['gap_status'] == 'not_measured'
    with pytest.raises(ValueError):
        rejection('')


def test_mac_execution_rejected_before_importing_physics(tmp_path, monkeypatch):
    from scripts import run_e2e_warp as runner
    monkeypatch.setattr(runner.platform, 'system', lambda: 'Darwin')
    a = type('Args', (), dict(e2e_warp_batch='on_v1'))()
    with pytest.raises(ValueError, match='Mac step/render prohibited'):
        runner.admit(a, dict(enabled=True))


def test_vendored_backend_core_abi_and_exact_control_clock():
    # Import/bind only. No MuJoCo/MJWarp import, model, step or render.
    from scripts.e2e_warp_physics import source_module
    backend, core, schedule = source_module()
    assert callable(core.multi_control_tape)
    assert callable(backend.WarpTransport.prepare_step)
    assert schedule.physics_schedule(.1, .00025) == (400, 16, 25)


def test_relay_uses_existing_journal_contract_and_deduplicates(tmp_path):
    from scripts.e2e_warp_relay import forward
    from scripts.openrouter_upstream import OpenRouter
    sent=[]
    def upstream_send(payload, key):
        sent.append(payload)
        return 200, json.dumps(dict(provider='CoreWeave',choices=[dict(finish_reason='stop',
            message=dict(content='{"act":"wait","message":null}'))],usage=dict(prompt_tokens=100,total_tokens=105))).encode(), None
    upstream=OpenRouter(tmp_path/'upstream',key='unit-test',send=upstream_send)
    planner=Planner('http://127.0.0.1:1',tmp_path/'client',{},run_id='e2ewarp-test',world_id=0,robot='r1')
    raw=json.dumps(planner.body(frame(),{'candidates':[{'id':'wait'}]})).encode()
    for _ in range(2):
        status,response,_=forward(upstream,raw,'e2ewarp-test:w0:r1:1')
        assert status==200 and json.loads(response)['provider']=='CoreWeave'
    assert len(sent)==1
    assert sent[0]['provider']==dict(order=['CoreWeave'],allow_fallbacks=False,quantizations=['fp4'])


def test_local_relay_contract_failure_is_immediate_host_error(tmp_path):
    from urllib.error import HTTPError
    def reject(*a,**k):
        raise HTTPError('http://127.0.0.1:1',400,'bad contract',{},io.BytesIO(json.dumps(
            dict(error='idempotency_key_required',host_error=True,ugrp_upstream_forwarded=False)).encode()))
    p=Planner('http://127.0.0.1:1',tmp_path/'client',{},run_id='e2ewarp-test',world_id=0,robot='r1',http_open=reject)
    with pytest.raises(RuntimeError,match='LOCAL_RELAY_CONTRACT'):
        p.decide(frame(),{'candidates':[]})


def mission_fixture():
    from harness.active_camera import SEARCH
    from harness.e2e_warp_mission import IntegratedController
    from harness import grasp_act_contract as c
    command=dict(t=0.,wheels=[0.]*4,duration_s=[0.]*4,pwm={str(k):v for k,v in SEARCH.items()})
    instruction=dict(order_id='one',object_kind='cyan',role='west',destination_zone='A',route='west',participants=['r1'])
    class Navigation:
        def __init__(self):
            self.report={'evidence_revision':'initial'};self.starts=[];self.confirm=True;self.messages=[]
        def observe(self, f):return self.report.copy()
        def task_candidates(self, completed):
            return ([dict(id='finish',skill='finish',expected_cost='own completion claim')]
                    if completed else [dict(id='task',skill='transport',instruction=instruction,expected_cost='own route')])
        def start(self, instruction, phase):self.starts.append((phase,instruction.copy()))
        def command(self, now):return {**command,'t':now}
        def confirm_act(self, f, skill):return self.confirm
        def on_messages(self, rows):self.messages.extend(rows)
        def accept_release_fix(self, report):return report.get('static_map_registered') is True
    class Release:
        def __init__(self):self.report={};self.views=0
        def start(self, instruction, report):pass
        def observe(self, f):self.views+=1;return self.report.copy()
        def command(self, now):return {**command,'t':now}
    calls=[]
    def predict(obs,jpegs):
        assert set(obs)==c.FIELDS and len(jpegs)==4 and obs['robot_id']=='r1'
        calls.append(obs)
        return [c.encode_action(command,done=True)]*c.CHUNK
    nav,release=Navigation(),Release()
    controller=IntegratedController('r1',{},predict,nav,release)
    def observe(t):
        return controller.observe(OwnFrame('r1',0,round(t*10),t,b'own-rgb',({**command,'t':t},)))
    def choose(candidate,t):controller.candidates();controller.select(candidate,t)
    return controller,nav,release,calls,observe,choose


def test_mission_requires_llm_authorizations_and_real_release_fix():
    ctl,nav,release,calls,observe,choose=mission_fixture()
    observe(0);choose('task',0);assert ctl.phase=='APPROACH'
    nav.report['handoff_ready']=True;observe(.1);assert ctl.phase=='GRASP_AUTH'
    choose('grasp',.1);ctl.command(.1);assert ctl.phase=='CARRY_AUTH'
    choose('carry',.1);assert nav.starts[-1][1]['route']=='west'
    nav.report['destination_arrived']=True;observe(.2);assert ctl.phase=='RELEASE_AUTH'
    choose('release',.2);ctl.command(.2);assert ctl.phase=='RELOCALIZE'
    observe(.3);assert ctl.phase=='RELOCALIZE' and not ctl.completed
    release.report={'relocalized':True,'static_map_registered':True}
    observe(.4);assert ctl.phase=='TASK' and len(ctl.completed)==1
    choose('finish',.4);assert ctl.complete
    assert len(calls)==2 and [r['skill'] for r in calls]==['grasp','release']


def test_act_done_without_rgb_confirmation_returns_unknown():
    ctl,nav,release,calls,observe,choose=mission_fixture()
    observe(0);choose('task',0);nav.report['handoff_ready']=True;observe(.1)
    choose('grasp',.1);nav.confirm=None;ctl.command(.1)
    assert ctl.phase=='UNCERTAIN' and not ctl.complete
    assert 'carry' not in {r['id'] for r in ctl.candidates()}


def test_wait_wakes_only_on_own_semantic_event_or_channel_message():
    ctl,nav,release,calls,observe,choose=mission_fixture()
    observe(0);choose('wait',0);assert not ctl.needs_decision
    observe(.1);assert not ctl.needs_decision
    ctl.receive([dict(sender='r2',body={'text':'준비됐어'})])
    assert ctl.needs_decision and len(nav.messages)==1


def test_owner_release_adapter_stays_off_and_cannot_claim_map_fix():
    from scripts.e2ewarp_vendor.release_reloc_selfmap import ReleaseSelfmap
    release=ReleaseSelfmap({}, {}, method='off')
    assert release.decision()['accepted'] is False
    with pytest.raises(ValueError,match='EXPLICIT_RELEASE_SELFMAP'):
        release.observe(0,None,{})


def test_qualified_frames_off_the_integer_second_are_not_all_lost():
    from harness.e2e_warp_runtime import keyframe_due
    qualified_ticks=[24,48,72,96]
    assert not any(keyframe_due(t,None,10) for t in qualified_ticks)
    last=None;admitted=[]
    for tick in qualified_ticks:
        if keyframe_due(tick,last,10,option='elapsed_sim_v1'):
            admitted.append(tick);last=tick
    assert admitted==qualified_ticks
    h=ConnectionHealth();h.observe(False,0)
    with pytest.raises(RuntimeError,match='LLM_CONNECTION_LOST'):
        h.check(30.1)  # no second model call is needed to enforce disconnect stop
