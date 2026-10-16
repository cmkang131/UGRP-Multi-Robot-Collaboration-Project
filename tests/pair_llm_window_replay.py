"""Cheap fake-controller replay through the real pair trial, transport and event scheduler."""
import copy
import hashlib
import json

from harness import pair_llm_contract as contract
from harness.pair_llm_case import stub_adapter
from harness.pair_llm_decisions import DecisionWindow
from harness.pair_llm_dispatch import PairTrial
from harness.pair_llm_stub import StubModel
from harness.zone_study_inputs import belief_skeleton
from harness.zone_study_integration import OwnFrame
from tests.pair_llm_fakes import make_inputs


class ReplayLink:
    def __init__(self, rid, jpeg, origin=0.):
        self.robot_id, self.origin_s, self.now, self.jpeg = rid, origin, 0., jpeg
        self.decision_window = DecisionWindow()
        self.stopped, self.call_ref = False, None
        self.command_log = []

    def clock(self):
        return self.now

    def frame_at(self, t):
        # A fake camera repeating the same synthetic image, no renderer or world.
        return OwnFrame(round(t*10)+1, t, self.jpeg, hashlib.sha256(self.jpeg).hexdigest())

    def belief(self):
        return belief_skeleton()

    def own_belief(self):
        from harness.pair_llm_stop_adapter import unknown_belief
        return unknown_belief()

    def job(self):
        return None if self.stopped else {'kind': 'pair_carry', 'order_id': 'cargoX', 'job_id': 'own-job'}

    def gate_view(self):
        return {'permit_released_at_sim_s': None, 'last_event': None, 'refusal_total': 0}

    def call(self, api, *args):
        assert api in ('hold', 'abort'), api
        self.stopped = api == 'abort'
        self.command_log.append((self.now, api, list(args)))
        return {'robot_id': self.robot_id, 'api': api, 'action_id': f'{self.robot_id}-stop',
                'sim_s': round(self.now+self.origin_s, 6), 'arguments': {}, 'accepted': True,
                'rejected_reason': None, 'job_id': None, 'local_state': 'command_issued'}

    def control_tick(self):
        # Nonempty replay trajectory; an accepted LLM abort changes every later command.
        return {'kind': 'hold'} if self.stopped else {'kind': 'drive', 'forward': round(self.now*10)%3,
                                                     'turn': 0 if self.robot_id == 'r1' else 1}


def event(rid, kind, t, *, origin=0., **detail):
    return {'robot_id': rid, 'event': 'pair_progress', 'sim_s': t+origin, 'job_kind': 'pair_carry',
            'job_id': 'own-job', 'scheduler_trigger': None, 'detail': {'kind': kind, **detail}}


def replay(tmp_path, *, condition='peer_nl', legacy=False, origin=0., stop=12., duration=24., policy=None,
           event_kind='carry_stop_reached'):
    bundled, _, bundle = make_inputs('no_comm')
    links = {r: ReplayLink(r, bundled.wrist_jpeg, origin) for r in ('r1', 'r2')}
    trial = None
    if condition != 'rule':
        model = StubModel(policy or (lambda *a: ({'kind': 'continue'}, [])))
        adapter, _ = stub_adapter(model, tmp_path/'ledger')
        trial = PairTrial(contract.scenario(), condition=condition, seed=911, links=links,
                          horizon_s=duration, map_bundle=bundle, model_adapter=adapter,
                          model_settings={'model': 'fake'})
        if legacy:
            trial.scheduler.event_available_at = lambda actor, cause: (
                float('inf') if cause and links[actor].job() is not None else trial.scheduler.clock)
        trial.begin(0.)
    commands = []
    for i in range(1, round(duration*10)+1):
        t = round(i/10, 6)
        for link in links.values():
            link.now = t
        if stop is not None and abs(t-stop) < 1e-8:
            for rid in links:
                detail = ({'decide_at_s': t+origin+10., 'latch_until_s': t+origin+9.8}
                          if event_kind == 'carry_stop_reached' else {'window_until_s': t+origin+10.})
                own = event(rid, event_kind, t, origin=origin, **detail)
                if trial is not None:
                    trial.on_executor_event(own, at_s=t)
        if trial is not None:
            trial.step_to(t)
        commands.extend((t, r, copy.deepcopy(link.control_tick())) for r, link in links.items())
    if trial is not None:
        trial.finish(duration)
    return trial, json.dumps(commands, sort_keys=True, separators=(',', ':')).encode()
