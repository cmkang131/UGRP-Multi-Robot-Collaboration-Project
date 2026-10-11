"""No model network, MuJoCo compile/render/step, or vision workers."""
import copy
import json
from types import SimpleNamespace
import pytest
from harness import s4_live_stage as stage
from harness import s4_llm_inputs as si
from harness.s4_live_transport import validate_receipt
from harness.zone_pilot_budget import PROXY_SHA256
from harness.zone_study_llm_driver import HostError
from tests.test_pair_llm_s4_host import make_host, advance, setup_data, RecordedWire, no_external_work
from tests.test_pair_llm_s4_host import StubS3Link
from harness.zone_study_integration import OwnFrame


@pytest.mark.parametrize('condition', stage.CONDITIONS)
def test_four_conditions_same_real_scheduler_and_claim_path(tmp_path, setup_data, condition):
    host, inner, _, _ = make_host(tmp_path, setup_data, arm=condition, wire=RecordedWire())
    host.begin(); advance(host, inner, 0, 25)
    assert all(len(link.calls)==1 for link in inner.values())
    assert host.trial.send_ledger.sends()==3
    assert host.trial.condition==condition
    bills=[r['billed_tokens']['system_billed'] for r in host.trial.requests]
    assert len(set(bills))==1
    if condition=='leader_ko': assert host.trial.leader_id=='r2'
    if condition=='no_comm': assert host.trial.channel.cap_total==0


def link():
    inner=SimpleNamespace(robot_id='r3', active=False, order={'order_id':'order-1','destination_zone':'A'})
    return stage.Link(inner,condition='no_comm')


@pytest.mark.parametrize('requested,now,accepted', [(10.,12.,True),(9.9,12.,False),(10.,20.,False)])
def test_departure_requires_fresh_current_decision(requested,now,accepted):
    own=link(); own.departure_opened=10.
    row=own.decide_departure(requested_at=requested,now=now,call_id='test')
    assert row['accepted'] is accepted and own.departure_accepted is accepted
    if accepted: assert not own.decide_departure(requested_at=10.,now=13.,call_id='duplicate')['accepted']


def test_relay_identity_and_expiry_fail_closed():
    r=dict(schema='ugrp.s4_ssh_proxy.v1',remote_url='http://127.0.0.1:18391/v1/chat/completions',
        proxy={'source_sha256':PROXY_SHA256},checked_unix=100.,audit_per_post=True,
        authentication='existing_mac_proxy_no_credentials_transferred')
    assert validate_receipt(r,now=101.)==r
    with pytest.raises(HostError): validate_receipt(r,now=3701.)
    r['proxy']['source_sha256']='0'*64
    with pytest.raises(HostError): validate_receipt(r,now=101.)


def test_common_prompt_blocks_and_equal_fixed_charge():
    prompts=[si.system_prompt(c,'r3',seed=601) for c in stage.CONDITIONS]
    for prompt in prompts:
        assert si.HEAD.format(rid='r3') in prompt
        assert si.ACTION in prompt and 'S4_DEPARTURE_PENDING' in prompt
    assert si.fixed_prompt_tokens(12,6,601)>=max(si.pk.count_tokens(p) for p in prompts)


def test_stage_claim_then_fresh_continue_opens_departure(tmp_path, setup_data):
    old, _, _, _=make_host(tmp_path, setup_data, wire=RecordedWire())
    inner={r:StubS3Link(r) for r in si.ROBOTS}
    for r, own in inner.items():
        own.order={'order_id':'order-1' if r=='r3' else 'order-5',
                   'destination_zone':'A' if r=='r3' else 'B'}
    links={r:stage.Link(inner[r], condition='no_comm',
        executor=old.links[r].stop_adapter.executor if r!='r3' else None) for r in inner}
    # Fresh ledger owner: reuse the factory/budget, with a separate transport.
    ledger=old.trial.send_ledger
    ledger._owner=None; ledger._authorize=None
    host=stage.Host(setup_data[0],condition='no_comm',links=links,seed=601,map_bundle=setup_data[1],
        model_adapter=stage.s4.zi.ModelAdapter(old.trial.client_factory,ledger),horizon_s=60.)
    for link_ in links.values(): link_.capture_frame()
    host.begin()
    for i in range(1,601):
        t=i/10
        for own in inner.values(): own.now=t
        for link_ in links.values(): link_.capture_frame()
        if t==25.: host.trial.open_departure(t)
        host.step_to(t)
    assert inner['r1'].s3_calls==inner['r2'].s3_calls==[]
    assert inner['r3'].s3_calls==[('deliver',('order-1','A'))]
    assert links['r3'].departure_accepted
    assert any(d.get('departure_gate',{}).get('accepted') for d in host.trial.dispatch_log)


def test_frame_selects_prior_own_capture_for_fractional_scheduler_time():
    own=link(); own.frames.extend([OwnFrame(1,1.,b'a','x'),OwnFrame(2,1.05,b'b','y')])
    assert own.frame_at(1.025).index==1
    assert own.frame_at(.99) is None
