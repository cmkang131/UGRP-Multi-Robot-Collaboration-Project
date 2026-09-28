"""Eval-only referee and hidden-event hooks of the integrated zone study (B6, #224).

No physics step runs here. The referee is fed synthetic truth rows; the episode
loop (``run_loop``) runs over a fake host around real ``ZoneOwnExecutor`` links
(the ``test_zone_study_integration`` pattern); the MuJoCo hooks run on a tiny
model with ``mj_forward`` only.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness import zone_study_contract as A  # noqa: E402
from harness import zone_study_eval as ev  # noqa: E402
from harness import zone_study_integration as zi  # noqa: E402
from harness import zone_study_referee as zr  # noqa: E402
from harness.zone_study_scenarios import load_all  # noqa: E402
from scripts import run_zone_study_integration as runner  # noqa: E402
from tests.test_zone_study_integration import BUNDLE, MAP, SCENARIO, SEED, links_for, requests_of  # noqa: E402

ZONE = {z: MAP['regions'][f'zone_{z}'] for z in 'ABC'}
I1_TARGET = {o['order_id']: o['destination_zone'] for o in SCENARIO['orders']}


def row(kind='cyan', x=0., y=0., yaw=0., z=.016, held=False, speed=0.):
    return {'kind': kind, 'x': x, 'y': y, 'yaw': yaw, 'z': z, 'held': held, 'speed': speed}


def at_zone(zone, **kw):
    cx, cy = ZONE[zone]['center_m']
    return row(x=cx, y=cy, **kw)


def feed(ref, t0, t1, items, dt=.1):
    t = t0
    while t <= t1 + 1e-9:
        ref.observe(round(t, 4), items(round(t, 4)) if callable(items) else items)
        t += dt


# ---------------------------------------------------------------- the delivery rule
def test_settled_unheld_item_inside_the_zone_is_delivered_at_the_start_of_the_window():
    ref = zr.Referee(SCENARIO['orders'], MAP)
    feed(ref, 1., 1.9, {'box_00': at_zone('A', held=True)})          # still gripped
    feed(ref, 2., 3.9, {'box_00': at_zone('A')})                     # released, 1.9 s < SETTLE_S
    assert not ref.history
    feed(ref, 4., 4., {'box_00': at_zone('A')})
    assert [(r['item_id'], r['zone'], r['sim_s'], r['confirmed_sim_s']) for r in ref.history] == \
        [('box_00', 'A', 2.0, 4.0)]
    assert ref.per_order()['order-3']['completed_sim_s'] == 2.0 and not ref.orders_complete()


@pytest.mark.parametrize('bad', [dict(z=.09), dict(speed=.05), dict(held=True)])
def test_lifted_moving_or_held_items_are_never_delivered(bad):
    ref = zr.Referee(SCENARIO['orders'], MAP)
    feed(ref, 0., 5., {'box_00': at_zone('A', **bad)})
    assert not ref.history


def test_landing_extents_not_the_centre_decide():
    """A long beam whose centre is in zone A but whose landing rectangle sticks out is not delivered."""
    orders = [{'order_id': 'o', 'kind': 'long_beam', 'count': 1, 'identity': 'specific_item',
               'item_ids': ['beam_1'], 'destination_zone': 'A'}]
    ref = zr.Referee(orders, MAP)
    cx, cy = ZONE['A']['center_m']
    # 0.6 m beam across the 0.6 m wide zone, centre 1 cm off: centre in, one end out.
    across = row('long_beam', cx + .01, cy, yaw=0.)
    along = row('long_beam', cx + .01, cy, yaw=math.pi / 2)
    assert ref.zone_of(across) is None and ref.zone_of(along) == 'A'
    box_edge = row(x=cx + ZONE['A']['half_extents_m'][0] - .005, y=cy)   # centre in, box half-width out
    assert ref.zone_of(box_edge) is None


def test_departure_undoes_a_delivery_and_a_bump_does_not():
    ref = zr.Referee(SCENARIO['orders'], MAP)
    feed(ref, 0., 2., {'box_00': at_zone('A')})
    feed(ref, 2.1, 2.1, {'box_00': at_zone('A', speed=.2)})           # bumped but still in A
    assert list(ref.standing) == ['box_00']
    feed(ref, 2.2, 2.2, {'box_00': at_zone('A', held=True)})          # picked up again
    assert not ref.standing and ref.history[-1]['event'] == 'departed'
    record = zr.apply_to_record({'orders': SCENARIO['orders'], 'end_sim_s': 3., 'end_reason': 'sim_horizon'}, ref)
    assert ev.delivery_state({**record, 't0_sim_s': 0.})['delivered'] == {}


def test_orders_complete_only_when_every_order_is_filled_and_success_comes_from_the_referee():
    ref = zr.Referee(SCENARIO['orders'], MAP)
    items = {'box_00': at_zone('A'), 'box_02': at_zone('B'), 'box_05': at_zone('B')}
    feed(ref, 0., 3., items)
    assert not ref.orders_complete()                                  # C is empty; the extra B is surplus
    feed(ref, 3.1, 6., {**items, 'box_05': at_zone('C')})
    assert ref.orders_complete() and ref.completion_sim_s() == 3.1 and ref.completed_at == 5.1
    rec = zr.apply_to_record({'orders': SCENARIO['orders'], 'end_sim_s': 6., 'end_reason': 'sim_horizon'}, ref)
    assert rec['end_reason'] == 'orders_complete' and rec['end_sim_s'] == 3.1
    assert {o: v['completed_sim_s'] for o, v in ref.per_order().items()} == \
        {'order-1': 3.1, 'order-2': 0.0, 'order-3': 0.0}


# ---------------------------------------------------------------- the episode loop
class FakeHost:
    """Physics owner stand-in: own executors of FakeLinks, truth from a function, no physics."""

    def __init__(self, links, clock, truth, hidden=None):
        self.links, self.clock, self.truth = links, clock, truth
        self.robots = {r: SimpleNamespace(dead=False) for r in links}
        self.hidden = hidden or zr.HiddenEventSchedule({'eval': {'hidden_events': []}})
        self.fired, self.truth_reads = [], 0

    def hidden_tick(self, t):
        self.fired += [(t, e['event_id']) for e in self.hidden.due(t)]

    def advance_to(self, t):
        self.clock[0] = t
        return [e for link in self.links.values() for e in link.ex.drain_events()]

    def referee_truth(self):
        self.truth_reads += 1
        return self.truth(self.clock[0])


def episode(condition, truth, *, horizon=30., hidden=None):
    clock = [1.3]
    links = links_for(clock)
    trial = zi.IntegratedTrial(SCENARIO, condition=condition, seed=SEED, links=links, horizon_s=horizon,
                               map_bundle=BUNDLE)
    host = FakeHost(links, clock, truth, hidden)
    ref = zr.Referee(SCENARIO['orders'], MAP)
    trial.begin(1.3)
    stop, t = runner.run_loop(host, trial, ref, 1.3, horizon)
    return trial, trial.finish(t), ref, host, stop, t


def never(t):
    return {'box_00': row(), 'box_02': row(), 'box_05': row()}


def done_at(t_done):
    def truth(t):
        if t < t_done:
            return never(t)
        return {'box_00': at_zone('A'), 'box_02': at_zone('B'), 'box_05': at_zone('C')}
    return truth


def _study_view(trial, before):
    """What each robot got and did: requests, wake-ups, dispatches, messages before ``before``."""
    return {rid: ([r['request_sha256'] for r in requests_of(trial, rid) if r['sim_s'] < before - 1e-9],
                  [w for w in trial.wakeups(rid) if w[0] < before - 1e-9],
                  [(d['sim_s'], d['api'], d['args']) for d in trial.dispatch_log
                   if d['actor'] == rid and d['sim_s'] < before - 1e-9])
            for rid in A.ROBOTS} | {'messages': [m['body'] for m in trial.messages if m['created_at_sim_s'] < before - 1e-9]}


@pytest.mark.parametrize('condition', A.MAIN_CONDITIONS)
def test_completion_only_stops_the_episode_and_never_reaches_a_robot(condition):
    base, _, _, host_a, stop_a, _ = episode(condition, never)
    done, result, ref, host_b, stop_b, t_end = episode(condition, done_at(8.))
    assert stop_a != 'orders_complete' and stop_b == 'orders_complete'
    assert t_end == pytest.approx(8. + zr.SETTLE_S) and host_b.truth_reads > 0
    # Everything a robot saw or did up to the stop is identical with and without completion.
    assert _study_view(base, t_end) == _study_view(done, t_end)
    assert _study_view(done, t_end)['r1'][0]                          # the comparison is not vacuous
    # No robot request carries referee output, completion or hidden-event data.
    for req in done.requests:
        text = json.dumps(req, ensure_ascii=False)
        for word in ('orders_complete', 'referee', 'confirmed_sim_s', 'hidden_event', 'par_makespan'):
            assert word not in text, word
    record = zr.apply_to_record(done.trial_record(result), ref)
    assert record['end_reason'] == 'orders_complete'
    ev_block = zr.evaluation_block(record, ref)
    assert ev_block['success'] and ev_block['par_makespan_sim_s'] == pytest.approx(8.)
    assert ev_block['delivery_rate'] == 1.0 and ev_block['orders']['order-1']['completed_sim_s'] == 8.


def test_failure_is_charged_twice_the_horizon_with_partial_delivery_rate():
    truth = lambda t: {**never(t), 'box_00': at_zone('A')}           # noqa: E731
    trial, result, ref, _, stop, _ = episode('no_comm', truth, horizon=12.)
    assert stop == 'horizon'
    block = zr.evaluation_block(zr.apply_to_record(trial.trial_record(result), ref), ref)
    assert not block['success'] and block['par_makespan_sim_s'] == pytest.approx(24.)
    assert block['delivery_rate'] == pytest.approx(1 / 3)


def test_hidden_events_fire_on_sim_time_and_change_no_robot_input():
    scenario = {'eval': {'hidden_events': [
        {'event_id': 'e1', 'kind': 'robot_hold', 'trigger': {'kind': 'sim_time', 'at_sim_s': 5.0},
         'target': {'robot_id': 'r3', 'duration_s': 4.}, 'discovery': {'kind': 'own_camera_self'}}]}}
    base, *_ = episode('peer_ko', never, horizon=12.)
    with_events, _, _, host, _, _ = episode('peer_ko', never, horizon=12., hidden=zr.HiddenEventSchedule(scenario))
    assert host.fired == [(5.0, 'e1')]
    assert _study_view(base, 12.) == _study_view(with_events, 12.)


# ---------------------------------------------------------------- separation (static)
def test_the_study_layer_never_imports_the_referee():
    from harness.python_source_closure import source_closure
    closure = source_closure(ROOT, ['harness/zone_study_integration.py', 'harness/zone_study_offline.py'])
    assert 'harness/zone_study_referee.py' not in closure
    assert 'harness/zone_study_referee.py' in source_closure(ROOT, ['scripts/run_zone_study_integration.py'])
    assert not hasattr(zi.IntegratedTrial, 'referee')


def test_referee_and_hidden_event_outputs_are_forbidden_robot_input_keys():
    ref = zr.Referee(SCENARIO['orders'], MAP)
    feed(ref, 0., 2., {'box_00': at_zone('A')})
    assert A.forbidden_key_hits({'referee': ref.record()})
    assert A.forbidden_key_hits({'hidden_events': []})
    assert {'referee', 'hidden_event_schedule'} <= ev.FORBIDDEN_INPUT_KEYS


# ---------------------------------------------------------------- scenario hidden events
def test_scenario_hidden_events_are_scheduled_in_sim_order():
    scenarios = load_all()
    kinds = {sid: [e['kind'] for e in zr.HiddenEventSchedule(s).events] for sid, s in scenarios.items()}
    assert kinds['s2_unmapped_blockage'] == ['passage_blocked']
    assert kinds['s3_late_rendezvous'] == ['robot_hold']
    assert kinds['s5_moved_dropped_item'] == ['item_moved', 'item_dropped']
    assert not kinds['s1_normal_mixed'] and not kinds['s4_narrow_door_standoff']
    s5 = zr.HiddenEventSchedule(scenarios['s5_moved_dropped_item'])
    assert s5.due(29.9) == [] and [e['event_id'] for e in s5.due(30.)] == ['cyan_1_moved']
    assert [e['event_id'] for e in s5.due(100.)] == ['red_1_dropped'] and s5.due(200.) == []
    s2 = zr.HiddenEventSchedule(scenarios['s2_unmapped_blockage'])
    assert [o['obstacle_id'] for o in s2.obstacles()] == ['fallen_pallet_1']
    assert s2.config()['sha256'] != s5.config()['sha256']


MJCF = """<mujoco><worldbody><geom name="floor" type="plane" size="5 5 .1"/>
<body name="item_body" pos="0 0 .016"><freejoint/><geom name="item_body_geom" type="box" size=".017 .02 .016"/></body>
<body name="r1_hand" pos="0 0 .016"><geom name="r1__left_finger" type="box" size=".005 .005 .005" pos="0 .02 0"/>
<geom name="r1__right_finger" type="box" size=".005 .005 .005" pos="0 -.02 0"/></body>
</worldbody></mujoco>"""


def tiny_host(held):
    mujoco = pytest.importorskip('mujoco')
    obstacle = {'obstacle_id': 'p1', 'center_m': [1., 1.], 'half_extents_m': [.1, .2], 'height_m': .12}
    xml = runner.hidden_obstacle_xml([obstacle])(MJCF if held else MJCF.replace('pos="0 0 .016"><geom', 'pos="3 3 .016"><geom'))
    model = mujoco.MjModel.from_xml_string(xml)
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)                                     # no physics step
    host = runner.StudyTeamHost.__new__(runner.StudyTeamHost)
    gid = lambda n: mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, n)   # noqa: E731
    stops = []
    host.world = SimpleNamespace(model=model, data=data)
    host.objects = {'it': {'kind': 'cyan', 'body_name': 'item_body'}}
    host._box_geom = {'it': {gid('item_body_geom')}}
    host._fingers = {r: ({gid('r1__left_finger')}, {gid('r1__right_finger')}) if r == 'r1' else (set(), set())
                     for r in A.ROBOTS}
    host.robots = {r: SimpleNamespace(port=SimpleNamespace(stop=lambda r=r: stops.append(r))) for r in A.ROBOTS}
    host.hidden_log, host._hold_until, host._drop_restore, host._parked = [], {}, [], {}
    return host, model, data, obstacle, stops


def ev_row(kind, target, at=1.):
    return {'event_id': kind, 'kind': kind, 'trigger': {'kind': 'sim_time', 'at_sim_s': at}, 'target': target}


def test_hidden_event_hooks_act_on_the_world_only():
    host, model, data, obstacle, stops = tiny_host(held=False)
    assert 'hidden_obstacle__p1' in [model.body(i).name for i in range(model.nbody)]
    out = host.apply_hidden_event(ev_row('passage_blocked', {'passage': 'door_x', 'obstacle': obstacle}), 1.)
    assert out['effect'] == 'obstacle_moved' and list(data.mocap_pos[0]) == pytest.approx([1., 1., .06])
    assert host.apply_hidden_event(ev_row('passage_cleared', {'passage': 'door_x'}), 2.)['effect'] == 'obstacle_moved'
    assert data.mocap_pos[0][2] == runner.PARK_Z_M
    out = host.apply_hidden_event(ev_row('item_moved', {'item_id': 'it', 'to_pose_m': [.5, -.5, math.pi / 2]}), 3.)
    assert out['effect'] == 'item_moved' and list(data.body('item_body').xpos[:2]) == pytest.approx([.5, -.5])
    assert host.apply_hidden_event(ev_row('item_dropped', {'item_id': 'it'}), 4.)['effect'] == 'none_item_not_held'
    assert host.apply_hidden_event(ev_row('robot_hold', {'robot_id': 'r3', 'duration_s': 40.}), 5.)['until_sim_s'] == 45.
    assert stops == ['r3'] and host._hold_until == {'r3': 45.}
    truth = host.referee_truth()['it']
    assert set(truth) == zr.TRUTH_KEYS and truth['held'] is False


def test_item_dropped_disables_the_holders_finger_contacts_for_the_window():
    host, model, data, _, _ = tiny_host(held=True)
    assert host.referee_truth()['it']['held'] is True
    assert host.apply_hidden_event(ev_row('item_moved', {'item_id': 'it', 'to_pose_m': [1, 1, 0]}), 1.)['effect'] \
        == 'none_item_held'
    out = host.apply_hidden_event(ev_row('item_dropped', {'item_id': 'it'}), 2.)
    assert out['effect'] == 'finger_contacts_disabled' and out['holders'] == ['r1']
    fingers = sorted(host._fingers['r1'][0] | host._fingers['r1'][1])
    assert all(model.geom_contype[g] == 0 and model.geom_conaffinity[g] == 0 for g in fingers)
    host.hidden = zr.HiddenEventSchedule({'eval': {'hidden_events': []}})
    host.hidden_tick(2. + zr.DROP_WINDOW_S)
    assert all(model.geom_contype[g] == 1 and model.geom_conaffinity[g] == 1 for g in fingers)


def test_bundle_pins_the_referee_and_hidden_event_profiles():
    pre = runner.load_prereg(ROOT / 'experiments/2026-09-26-zone-study-integration/prereg.json')
    bundle = runner.run_bundle(pre, pre['episodes'][0])[0]
    assert bundle['execution_bundle_id'] == 'zone-study-integration-v72-referee-hidden-events'
    assert bundle['referee'] == zr.profile() and bundle['hidden_events']['events'] == []
    assert 'harness/zone_study_referee.py' in bundle['runtime_files_sha256']
    assert 'zone-study-integration-v69-multiturn-landmark-agnostic' in zi.RETIRED_BUNDLE_IDS
