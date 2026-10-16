"""vote_ref_v1: short GO/ACK reference expanded by the host (no physics, no provider)."""
import copy
import json
from types import SimpleNamespace
import pytest
from harness import e2e_s4_live as live
from harness import e2e_vote_ref as vr
from harness.s4_event_policy import Options
from harness.zone_study_contract import ContractViolation
from tests.test_e2e_dialogue import build
from tests.test_pair_llm_s4_host import setup_data, no_external_work, advance
from tests.test_e2e_acquire_standoff import _pan_parent

RH = 'a' * 64


def opened(tmp_path, setup_data, option):
    host, inner, wire = build(tmp_path, setup_data)
    advance(host, inner, 1, 4)
    d = host.trial.dialogue
    d.vote_ref = option
    d.proposal = dict(message_id='m1', origin='o1', route=dict(route_hash=RH))
    d.approved, d.claims = True, {'r1', 'r2'}
    d.begin_epoch(order_id='order-5', route_hash=RH, grip_epoch=1, seg=0, now=5.)
    return host, d


def ctx(d, actor='r1', now=6.):
    return dict(actor=actor, view=d.view(actor, now), requested_at=now, frame_t=now - .1, inbox=[], state={})


def test_view_carries_short_ref_only_when_enabled(tmp_path, setup_data):
    host, d = opened(tmp_path, setup_data, 'v1')
    v = d.view('r1', 6.)
    assert v['vote_ref'] == vr.ref_for(d.key) and len(v['vote_ref']) == 7
    d.vote_ref = 'off'
    assert 'vote_ref' not in d.view('r1', 6.)


def test_expansion_matches_full_vote_and_check_action_accepts(tmp_path, setup_data):
    host, d = opened(tmp_path, setup_data, 'v1')
    c = ctx(d)
    ref = c['view']['vote_ref']
    full = vr.expand(d, dict(kind='route_vote', choice='GO', vote_ref=ref), c)
    assert full == dict(kind='route_vote', choice='GO', order_id='order-5', route_hash=RH, grip_epoch=1, seg=0, peer_go_ref=None)
    d.check_action(full, c, 6.5)                                  # unchanged contract validation
    d.votes['r2'] = dict(GO=dict(call_id='peer-go', at=5.5, frame_t=5.4))
    c2 = ctx(d, 'r1', 7.)
    ack_missing_go = vr.expand(d, dict(kind='route_vote', choice='ACK', vote_ref=ref), c2)
    assert ack_missing_go['peer_go_ref'] == 'peer-go'
    with pytest.raises(ContractViolation, match='CAPTURED_PEER_GO'):
        d.check_action(ack_missing_go, c2, 7.5)                   # still needs own GO: host rules intact


@pytest.mark.parametrize('action,match', [
    (dict(kind='route_vote', choice='GO', vote_ref='vdeadbe'), 'VOTE_REF_MISMATCH'),
    (dict(kind='route_vote', choice='GO'), 'VOTE_REF'),
    (dict(kind='route_vote', choice='STOP', vote_ref=None), 'VOTE_REF_MISMATCH|MATCHING'),
    (dict(kind='route_vote', choice='GO', order_id='order-5', route_hash=RH, grip_epoch=1, seg=0, peer_go_ref=None), 'VOTE_REF'),
])
def test_wrong_or_full_form_is_rejected(tmp_path, setup_data, action, match):
    host, d = opened(tmp_path, setup_data, 'v1')
    with pytest.raises(ContractViolation, match=match):
        vr.expand(d, action, ctx(d))


def test_closed_window_is_rejected(tmp_path, setup_data):
    host, d = opened(tmp_path, setup_data, 'v1')
    c = ctx(d)
    action = dict(kind='route_vote', choice='GO', vote_ref=c['view']['vote_ref'])
    d.begin_epoch(order_id='order-5', route_hash=RH, grip_epoch=2, seg=0, now=8.)   # old window closed
    with pytest.raises(ContractViolation, match='VOTE_WINDOW_CLOSED'):
        vr.expand(d, action, c)
    d.key = None
    with pytest.raises(ContractViolation, match='VOTE_WINDOW_CLOSED'):
        vr.expand(d, action, c)
    nokey = dict(c, view=dict(c['view'], key=None))
    with pytest.raises(ContractViolation, match='VOTE_WINDOW_CLOSED'):
        vr.expand(d, action, nokey)


def test_off_and_other_actions_pass_through_unchanged(tmp_path, setup_data):
    host, d = opened(tmp_path, setup_data, 'off')
    full = dict(kind='route_vote', choice='GO', order_id='order-5', route_hash=RH, grip_epoch=1, seg=0, peer_go_ref=None)
    assert vr.expand(d, full, ctx(d)) is full
    d.vote_ref = 'v1'
    cont = dict(kind='continue')
    assert vr.expand(d, cont, ctx(d)) is cont


def test_prompt_off_is_identical_and_on_drops_hash_copy(tmp_path, setup_data):
    host, d = opened(tmp_path, setup_data, 'off')
    call = SimpleNamespace(call_id='vt-r1', actor='r1', started_sim_s=6.)
    host.trial.snapshot(call)
    original = host.trial.prepare_call(call).request
    opts = Options(True, True, 'en')
    default = live.project(original, options=opts)
    off = live.project(original, options=opts, vote_ref='off')
    assert off['request_sha256'] == default['request_sha256'] and off['messages'] == default['messages']
    assert 'vote_ref' not in json.dumps(off['messages'])
    on = live.project(original, options=opts, vote_ref='v1')
    system, user = on['messages'][0]['content'], json.loads(on['messages'][1]['content'])
    vote = next(a for a in user['action_message_contract']['actions'] if a['kind'] == 'route_vote')
    assert vote == dict(kind='route_vote', choice=['GO', 'ACK'], vote_ref='<dialogue.vote_ref>')
    assert 'dialogue.vote_ref' in system and 'order,' in system and vr.PROMPT_OLD not in system
    assert on['messages'][0]['content'].replace(vr.PROMPT_NEW, vr.PROMPT_OLD) == default['messages'][0]['content']
    with pytest.raises(ValueError):
        live.project(original, options=opts, vote_ref='v9')


def test_v314_v315_bundles(monkeypatch):
    from harness.e2e_runtime_registration import require_current
    from scripts.run_e2e_ownmap_live import ROOT, bundle
    args, kw = _pan_parent(monkeypatch)
    base = dict(kw, stage_physics='release_dt1_v1', relook_giveup='dev_light_v1', clip_hysteresis='v1')
    for extra, num, parent in (({'approach_floor': 'v1'}, 315, 'e2e18-v312'), ({}, 314, 'e2e18-v313')):
        b = bundle(*args, **dict(base, **extra, vote_ref='v1'))
        assert b['execution_bundle_id'] == f'e2e18-v{num}' and b['vote_ref_parent'] == parent
        assert b['e2e_options']['vote_ref'] == 'v1' and b['e2e_options']['clip_hysteresis'] == 'v1'
        assert 'harness/e2e_vote_ref.py' in b['source_sha256']
        require_current(b, ROOT)
        bad = copy.deepcopy(b); bad['e2e_options']['vote_ref'] = 'off'
        with pytest.raises(ValueError):
            require_current(bad, ROOT)
    with pytest.raises(ValueError):
        bundle(*args, **dict(kw, vote_ref='v1'))          # needs the v312/v313 parent
