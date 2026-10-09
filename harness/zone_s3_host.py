"""S3 fixed-role, no-model adapter. No world, private placements or referee inputs.

The pair's existing scheduler/barriers and the solo v106 state machine remain
the command producers. IntegratedTrial supplies three own links and the public
claim -> executor mapping, without arming its model/fixture scheduler.
"""
from __future__ import annotations

import base64
import copy
import hashlib
from types import MethodType, SimpleNamespace

from harness import zone_pair_role_integration as integration
from harness import zone_pair_highpose_runtime as pair
from harness import zone_final_pair_runtime as pair_base
from harness import zone_final_pair_skill as skill
from harness import zone_solo_cyan_v106 as solo
from harness.zone_final_pair_binding import bind
from harness.zone_own_contract import pickup_slots
from harness.zone_study_integration import OwnFrame
from harness.visual_arm_v3 import CONTROLLER_GEOMETRY_ID

ROBOTS = ('r1', 'r2', 'r3')
ROLES = {'end_neg': 'r1', 'end_pos': 'r2'}
PROFILE = 's3-fixed-role-script-v107'


def build_pair_provider(static, calibration, calibration_sha, seed=0, *, model_runtime=None, worker=None):
    """Explicit v3 consumer declaration around the unchanged pair provider."""
    return pair.provider_builder()(static, calibration, calibration_sha, seed, worker=worker)


build_pair_provider.controller_geometry_id = CONTROLLER_GEOMETRY_ID
build_pair_provider.uses_landmark_tags = False


def public_tasks(orders):
    """Accept only this DEV fixture's PUBLIC task vocabulary."""
    rows = {o['kind']: copy.deepcopy(o) for o in orders}
    if (len(orders) != 2 or set(rows) != {'cyan', 'long_beam'}
            or any(o['count'] != 1 for o in orders)
            or rows['cyan']['required_robots'] != 1
            or rows['long_beam']['required_robots'] != 2
            or rows['cyan']['destination_zone'] != 'A'
            or rows['long_beam']['destination_zone'] != 'B'):
        raise ValueError('S3 requires one cyan -> A and one long_beam -> B')
    return rows


def pair_task(static, order):
    """Search prior from the public slot and door axis, never private setup pose.

    The existing pair planner needs an approximate starting centre. Project the
    public slot centre onto door_1's public axis, clipped to the slot. This avoids
    an unnecessary bend in the bounded pair route; own RGB does final alignment.
    Its error against the actual beam is not corrected by the host.
    """
    slot = pickup_slots(static)[order['initial_location']['slot']]
    door = next(p for p in static['passages'] if p['id'] == 'door_1')
    lo, hi = slot['y_range_m']
    y = max(lo, min(hi, door['center_m'][1]))
    sheet = skill.m2.pa.coarse_order_sheet([slot['center_m'][0], y, 0.])
    sheet['source'] = 'public slot centre projected onto public door axis; fixed EW task; not measured cargo pose'
    alias = {**copy.deepcopy(order), 'order_id': 'cargoX'}
    return {'order': {'orders': [alias]}, 'sheet': sheet,
            'target': order['destination_zone'], 'beam_pose': list(sheet['beam_xyyaw'])}


class PairRuntime(pair.Runtime):
    """Private dependency binding, already used by the frozen v3 pair stack."""
    def __init__(self, static, calibration, calibration_sha, *, seed, order, provider_factory=None):
        task = pair_task(static, order)
        planner = bind(skill.make_plan, task=lambda _: task)
        # Fail before constructing providers if the PUBLIC prior has no static route.
        planner(static, task['sheet'], task['target'])

        class SlotTeam(pair.Team):
            def __init__(self, *args):
                super().__init__(*args)
                self.start = MethodType(bind(self.start.__func__, make_plan=planner), self)

        # Keep the parent's exact init, provider, frame gate and look recovery;
        # bind only its static task and team planner, never shared module globals.
        base_init = bind(pair_base.Runtime.__init__, task=lambda _: task)
        initialize = bind(pair.Runtime.__init__, PreviousRuntime=SimpleNamespace(__init__=base_init), Team=SlotTeam)
        initialize(self, static, calibration, calibration_sha, seed=seed,
                   provider_factory=provider_factory or build_pair_provider)


class OwnLink:
    """One IntegratedTrial RobotLink. It has no physics/evaluation capability."""
    def __init__(self, robot_id, runtime, order, *, submit=None):
        self.robot_id, self.runtime, self.order = robot_id, runtime, copy.deepcopy(order)
        self.submit = submit
        self.now, self.frame, self.active = 0., None, False

    def observe(self, now, frame):
        obs, _ = frame
        jpeg = base64.b64decode(obs['image'], validate=True)
        if (obs['robot_id'] != self.robot_id or obs['camera'] != 'robot_cam'
                or hashlib.sha256(jpeg).hexdigest() != obs['sha256']
                or abs(float(obs['sim_time'])-now) > 1e-8):
            raise ValueError('S3 foreign/corrupt/stale own frame')
        self.now = now
        self.frame = OwnFrame(obs['frame_id'], now, jpeg, obs['sha256'])

    def clock(self):
        return self.now

    def frame_at(self, t):
        return self.frame if self.frame and self.frame.t <= t+1e-9 else None

    def belief(self):
        if self.robot_id != 'r3':
            return self.runtime.actors[self.robot_id].belief_projection()
        r = self.runtime.last_report
        return {} if r is None else {'x_m': r.x_m, 'y_m': r.y_m, 'yaw_rad': r.yaw_rad,
                                     'std_xy_m': r.std_xy_m}

    def job(self):
        if self.robot_id == 'r3':
            return ({'kind': 'deliver', 'order_id': self.order['order_id']}
                    if self.active and not self.runtime.terminal else None)
        job = self.runtime.actors[self.robot_id].job
        return None if job is None else {'kind': job.kind, 'order_id': self.order['order_id']}

    def call(self, api, *args):
        expected = (self.order['order_id'], self.order['destination_zone'])
        if self.robot_id == 'r3':
            if api != 'deliver' or args != expected or self.active:
                raise ValueError('S3 solo role/task is fixed')
            self.active = True
            return {'accepted': True, 'robot_id': 'r3', 'api': api, 'local_state': 'command_issued',
                    'rejected_reason': None, 'order_id': expected[0]}
        role = next(k for k, r in ROLES.items() if r == self.robot_id)
        partner = next(r for r in ('r1', 'r2') if r != self.robot_id)
        if api != 'pair_carry' or args != (*expected, partner, role):
            raise ValueError('S3 pair role/task is fixed; K11 is not admitted')
        # Preserve the frozen runtime's internal cargoX identifier explicitly.
        ack = self.submit(self.robot_id, 'cargoX', expected[1], partner, now=self.now)
        return {**ack, 'public_order_id': expected[0], 'executor_order_alias': 'cargoX'}


class IntegratedTrial(integration.IntegratedTrial):
    """Opt-in scripted trial: no HTTP, fixture reply, model tokens or SIM think cost."""
    def __init__(self, scenario, *, seed, links, map_bundle, horizon_s, code_sha, pair_records):
        super().__init__(scenario, condition='no_comm', seed=seed, links=links,
                         map_bundle=map_bundle, horizon_s=horizon_s, code_sha=code_sha,
                         pair_role_assignment=ROLES, pair_records=pair_records)
        self.tasks = public_tasks(self.sheet['orders'])
        self.begun = False
        self.transport.submit = self._no_model

    @staticmethod
    def _no_model(*args, **kwargs):
        raise RuntimeError('S3 forbids model and fixture calls')

    prepare_call = _no_model
    _on_action = _no_model

    def begin(self, t0_s):
        if self.begun:
            raise ValueError('S3 trial already started')
        self.begun = True
        self.step_to(t0_s)
        self.claim('r3', t0_s)

    def step_to(self, t_s):
        # No scheduler trigger, timer or fixture transport is armed in S3.
        self.script_time = t_s

    def claim(self, actor, now):
        if not self.begun or actor not in ROBOTS:
            raise ValueError('S3 script is not active')
        order = self.tasks['cyan' if actor == 'r3' else 'long_beam']
        action = {'kind': 'claim', 'order_id': order['order_id'],
                  'destination_zone': order['destination_zone']}
        if actor != 'r3':
            action['role'] = next(k for k, r in ROLES.items() if r == actor)
        link = self.links[actor]
        link.now = now
        plan = integration.executor_plan(action, link.job(), actor=actor, orders=self.sheet['orders'],
                                         role_assignment=ROLES)
        if plan.rejected_reason or not plan.api:
            raise RuntimeError(f'S3 scripted claim refused: {plan.rejected_reason}')
        ack = link.call(plan.api, *plan.args)
        self.dispatch_log.append({'actor': actor, 'sim_s': now, 'source': 'fixed_role_script',
                                  'action': action, 'api': plan.api, 'args': list(plan.args), 'ack': ack})
        return ack

    def on_executor_event(self, event, *, at_s):
        # Own command events are records only: never a model wake or peer notification.
        self.executor_events.append(copy.deepcopy(event))

    def finish(self, t_end_s):
        if self.scheduler.calls or self.requests or self.send_ledger.sends():
            raise AssertionError('S3 generated a model/fixture call')
        return {'profile': PROFILE, 'condition': 'fixed_role_script', 'model_calls': 0,
                'http_attempts': 0, 'tokens': 0, 'model_response_time_s': 0.,
                'seed': self.seed, 'source_sha': self.code_sha, 'end_sim_s': t_end_s,
                'order_sheet': self.sheet, 'dispatch': self.dispatch_log,
                'pair_role_assignment': dict(ROLES), 'pair_status': self.pair_status.record(),
                'input_boundary': ['own_rgb', 'static_map', 'own_command_history'],
                'inter_robot_channels': ['existing_pair_fixed_enum_status'],
                'physical_success': None, 'research_result': False}


class Runtime:
    """Multiplex unchanged pair/solo producers on ONE host clock, no truth input."""
    def __init__(self, static, orders, calibration, calibration_sha, *, seed,
                 pair_factory=PairRuntime, solo_factory=solo.Runtime):
        tasks = public_tasks(orders)
        self.pair = self.solo = None
        self.trial, self.started = None, False
        self.event_offsets = {'r1': 0, 'r2': 0}
        try:
            self.pair = pair_factory(static, calibration, calibration_sha, seed=seed, order=tasks['long_beam'])
            self.solo = solo_factory(static, calibration, calibration_sha, seed=seed+2, robot_id='r3',
                pickup_slot=tasks['cyan']['initial_location']['slot'], destination='A', passage_id='door_1')
            submit = self.pair.team.start
            self.links = {r: OwnLink(r, self.pair, tasks['long_beam'], submit=submit) for r in ('r1', 'r2')}
            self.links['r3'] = OwnLink('r3', self.solo, tasks['cyan'])
            self.pair.team.start = self._pair_claim
        except Exception:
            self.close()
            raise

    def _pair_claim(self, rid, item_ref=None, target_zone=None, partner_id=None, *, now):
        if self.trial is None or item_ref != 'cargoX':
            raise ValueError('S3 pair claim without integrated trial')
        return self.trial.claim(rid, now)

    def initial_commands(self, now, commands):
        if set(commands) != set(ROBOTS):
            raise ValueError('S3 needs exactly three own reset command histories')
        self.pair.initial_commands(now, {r: copy.deepcopy(commands[r]) for r in ('r1', 'r2')})
        self.solo.initial_commands(now, {'r3': copy.deepcopy(commands['r3'])})

    def on_frames(self, now, frames):
        if set(frames) != set(ROBOTS):
            raise ValueError('S3 requires one own frame per robot')
        for r in ROBOTS:
            self.links[r].observe(now, frames[r])
        if not self.pair_ended:
            self.pair.on_frames(now, {r: frames[r] for r in ('r1', 'r2')})
        if not self.solo.terminal:
            self.solo.on_frames(now, {'r3': frames['r3']})

    @property
    def pair_ended(self):
        return all(any(j['kind'] != 'look_around' for j in own.jobs_done)
                   for own in self.pair.actors.values())

    @property
    def failures(self):
        out = dict(self.pair.look_recovery.failures())
        for r, own in self.pair.actors.items():
            for j in own.jobs_done:
                if j.get('confirmation') == 'failed' and j['kind'] != 'look_around':
                    out[r] = j['outcome']
        for session in self.pair.team.sessions:
            for r, ep in session['endpoints'].items():
                if ep.controller.failure:
                    out[r] = ep.controller.failure
        if self.solo.failure:
            out['r3'] = self.solo.failure
        return out

    @property
    def terminal(self):
        return bool(self.failures) or (self.pair_ended and self.solo.terminal)

    def step(self, now):
        if self.trial is None:
            raise ValueError('S3 runtime requires IntegratedTrial')
        self.trial.step_to(now)
        if self.terminal:
            return [(r, {'kind': 'hold'}) for r in ROBOTS]
        rows = ([(r, {'kind': 'hold'}) for r in ('r1', 'r2')] if self.pair_ended else self.pair.step(now))
        if not self.pair_ended:
            rows += self.pair.arm_step(now)  # same 0.05 s arm/status cadence as the existing pair host
        rows += self.solo.step(now) if self.links['r3'].active else [('r3', {'kind': 'hold'})]
        for r, own in self.pair.actors.items():
            for event in own.events[self.event_offsets[r]:]:
                self.trial.on_executor_event(event, at_s=now)
            self.event_offsets[r] = len(own.events)
        # A later endpoint failure in this same tick must veto earlier commands too.
        return [(r, {'kind': 'hold'}) for r in ROBOTS] if self.failures else rows

    def on_command(self, rid, now, action):
        if rid not in ROBOTS:
            raise ValueError('unknown S3 command owner')
        (self.solo if rid == 'r3' else self.pair).on_command(rid, now, action)

    def record(self):
        return {'profile': PROFILE, 'pair': self.pair.record(), 'solo': self.solo.record(),
                'pair_order_alias': {'cargoX': self.links['r1'].order['order_id']},
                'pair_public_search_prior': self.pair.task['sheet'], 'failures': self.failures,
                'physical_success': None, 'in_run_drop_tilt_contact_detection': False}

    def close(self):
        errors = []
        for runtime in (self.solo, self.pair):
            if runtime is not None:
                try:
                    runtime.close()
                except Exception as exc:
                    errors.append(str(exc))
        if errors:
            raise RuntimeError('; '.join(errors))
