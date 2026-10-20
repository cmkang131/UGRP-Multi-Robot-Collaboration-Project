"""P5 student controller: pure tests with a scripted fake policy (no torch, no simulator)."""
import base64
import io
import json

import pytest

from harness import grasp_act_contract as c
from harness import pairact_r1 as p
from harness import pairact_r1_student as s

ROLES = {'r1': 'teal', 'r2': 'blue'}
PWM = {str(k): 1500 for k in c.SERVOS}
INIT = {r: {'t': 0., 'wheels': [0.] * 4, 'duration_s': [0.] * 4, 'pwm': dict(PWM)} for r in ROLES}


class Script:
    """stage(obs) -> (stage name, done flag); actions keep PWM at 1500."""
    def __init__(self, fn):
        self.fn, self.calls = fn, []

    def __call__(self, observation, jpegs):
        self.calls.append(observation)
        stage, done = self.fn(observation)
        row = [0.] * 13 + [1. if done else 0.]
        logits = [[1. if k == p.STAGES.index(stage) else 0. for k in range(len(p.STAGES))]] * c.CHUNK
        return {'chunk': [row] * c.CHUNK, 'stage_logits': logits}


def tick(ctrl, t, permits=None, previous=None):
    robots = {r: {'jpeg': b'jpeg-%s-%d' % (r.encode(), round(t * 10)), 'issued': (previous or INIT)[r]} for r in ROLES}
    proposed = ctrl.propose(t, robots)
    ready = {r: v['ready'] for r, v in proposed.items()}
    issued = ctrl.issue(t, permits if permits is not None else {r: False for r in ROLES})
    return proposed, ready, issued


def test_request_allowlist_rejects_truth_and_partner_inputs():
    ctrl = s.PairStudentController(Script(lambda o: ('approach', False)), ROLES, 'ep', INIT)
    with pytest.raises(ValueError, match='own camera'):
        ctrl.propose(0., {r: {'jpeg': b'x', 'issued': INIT[r], 'truth': {}} for r in ROLES})
    with pytest.raises(ValueError, match='own camera'):
        ctrl.propose(0., {'r1': {'jpeg': b'x', 'issued': INIT['r1']}})


def test_ready_waits_for_permit_and_uses_wait_token():
    ctrl = s.PairStudentController(Script(lambda o: ('ready', False)), ROLES, 'ep', INIT)
    _, ready, issued = tick(ctrl, 0.)
    assert ready == {'r1': True, 'r2': True}
    assert all(v['command']['wheels'] == [0.] * 4 for v in issued.values())
    proposed, _, _ = tick(ctrl, .1)
    assert {v['observation']['skill'] for v in proposed.values()} == {'wait'}
    assert all(v['observation']['destination_zone'] == 'none' for v in proposed.values())


def test_both_done_for_three_seconds_switches_to_release_b_then_finishes():
    def fn(o):
        if o['skill'] == 'release':
            return ('place', o['skill_elapsed_s'] >= 1.)
        return ('ready', False) if o['t'] < .45 else ('execute', True)
    ctrl = s.PairStudentController(Script(fn), ROLES, 'ep', INIT, done_recovery='off')
    t, seen = 0., set()
    while t < 10 and not ctrl.finished:
        proposed, _, _ = tick(ctrl, t, permits={r: True for r in ROLES})
        seen |= {(v['observation']['skill'], v['observation']['destination_zone']) for v in proposed.values()}
        t = round(t + .1, 6)
    # done starts only after READY -> GO and the executor drains the READY chunk
    assert 3. + .5 <= ctrl.switch_t <= 3. + 1.3
    assert ('release', 'B') in seen and ('grasp', 'none') in seen
    assert ctrl.finished and ctrl.finish_t - ctrl.switch_t >= s.FINISH_AFTER_S
    summary = ctrl.summary()
    assert summary['teacher_actions'] == 0 and summary['truth_inputs'] == 0
    assert [e['event'] for e in summary['events']] == ['release_instruction', 'finished']


def test_one_robot_done_is_not_enough():
    ctrl = s.PairStudentController(Script(lambda o: ('execute', o['robot_id'] == 'r1')), ROLES, 'ep', INIT,
                                   done_recovery='off')
    for k in range(60):
        tick(ctrl, k * .1, permits={r: True for r in ROLES})
    assert ctrl.segment == 'grasp' and ctrl.switch_t is None


def test_observation_clock_is_v7_and_contract_valid():
    ctrl = s.PairStudentController(Script(lambda o: ('approach', False)), ROLES, 'ep', INIT)
    prev = {r: dict(INIT[r]) for r in ROLES}
    for k in range(5):
        # +-2 PWM dither in what the runner applied never resets pwm_elapsed_s
        prev = {r: {**prev[r], 't': k * .1, 'pwm': {**PWM, '3': 1500 + (2 if k % 2 else 0)}} for r in ROLES}
        ctrl.inputs['r1'].issued.append(c.command(prev['r1']))
        proposed, _, _ = tick(ctrl, k * .1, previous=prev)
    obs = proposed['r1']['observation']
    assert set(obs) == c.FIELDS
    assert obs['pwm_elapsed_s'] == pytest.approx(.4)


def test_place_sync_is_not_wired():
    with pytest.raises(NotImplementedError):
        s.PairStudentController(Script(lambda o: ('approach', False)), ROLES, 'ep', INIT, place_sync=p.PLACE_SYNC_MODE)


def test_worker_serve_roundtrip_and_allowlist():
    from scripts import pairact_r1_student_worker as w
    config = {'done_recovery': p.RECOVERY_MODE, 'place_sync': 'off', 'issued_clock_deadband': 2}
    b64 = lambda x: base64.b64encode(x).decode()
    lines = [json.dumps({'op': 'reset', 'roles': ROLES, 'episode_id': 'ep', 'initial': INIT}),
             json.dumps({'op': 'propose', 't': 0., 'robots': {r: {'jpeg': b64(b'a'), 'issued': INIT[r]} for r in ROLES}}),
             json.dumps({'op': 'issue', 't': 0., 'permits': {r: False for r in ROLES}}),
             json.dumps({'op': 'summary'})]
    out = []
    w.serve(Script(lambda o: ('alignment', False)), lines, out.append, config=config)
    replies = [json.loads(x) for x in out]
    assert replies[0] == {'ok': True}
    assert set(replies[1]['robots']['r1']) == {'ready', 'observation', 'rgb_path', 'stage'}
    assert replies[2]['finished'] is False and set(replies[2]['robots']) == set(ROLES)
    assert replies[3]['teacher_actions'] == 0
    with pytest.raises(ValueError, match='allowlist'):
        w.serve(Script(lambda o: ('approach', False)), [json.dumps({'op': 'propose', 't': 0., 'robots': {}, 'gt': 1})],
                out.append, config=config)


def test_release_switch_needs_both_flags_continuously_for_three_seconds():
    ctrl = s.PairStudentController(Script(lambda o: ('approach', False)), ROLES, 'ep', INIT)
    ctrl.done_since = {'r1': 0., 'r2': .5}
    ctrl._sequence(3.4)
    assert ctrl.segment == 'grasp'
    ctrl._sequence(3.5)
    assert ctrl.segment == 'release' and ctrl.switch_t == 3.5
