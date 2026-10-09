"""Opt-in mixed S3: three isolated v141 localizers, existing pair and door enums.

No setup pose is supplied, even temporarily. Pair actors retain the very same
own-image posterior acquired by their S2 startup scan; it is never Gaussianized
or replaced with a dock prior. Frozen v107/v108 entry points are unchanged.
"""
import copy
from types import MethodType, SimpleNamespace

from harness import zone_s3_host as old
from harness import zone_s3_door_yield as door
from harness.zone_final_pair_binding import bind

ROBOTS = old.ROBOTS


def carry_yaw_record(team):
    """S2 providers have no carry-yaw fallback; serialize absence as empty data."""
    from harness import owncam_carry_v6e as carry
    out = {}
    for rid, executor in team.executors.items():
        inner = carry._inner(executor.pose)
        edge = getattr(inner, 'beam_edge', None)
        fallback = getattr(inner, 'carry_yaw_fallback', None)
        out[rid] = dict(partner_plan_matched=int(getattr(inner.loc, 'pair_matched', 0)),
            partner_plan_unmatched=int(getattr(inner.loc, 'pair_unmatched', 0)),
            availability_frames=dict((fallback or {}).get('level_frames') or {}),
            **({'beam_edge': {**edge.stats, 'total_rad': edge.total_rad}} if edge is not None else {}))
    return out


def public_tasks(orders):
    rows = {o['kind']: copy.deepcopy(o) for o in orders}
    if (len(orders) != 2 or set(rows) != {'cyan', 'long_beam'}
            or any(o['count'] != 1 or o['destination_zone'] != 'B' for o in orders)
            or rows['cyan']['required_robots'] != 1 or rows['long_beam']['required_robots'] != 2):
        raise ValueError('S3 no-prior requires cyan and pair beam, both to B')
    return rows


def solo_factory(config):
    from scripts.run_s2_unknown_start import runtime_factory
    from harness.zone_solo_cyan_active_observation import attach as active
    from harness.zone_solo_cyan_rotation_envelope import attach as guard
    from harness.zone_s3_localization_certification import attach as certify
    from harness.zone_s3_recorded_camera import attach as recorded_camera
    plain = copy.deepcopy(config)
    a = plain['options'].pop('active_localization')
    g = plain['options'].pop('active_rotation_guard')
    certification = plain['options'].pop('localization_certification', 'off')
    mount = plain['options'].pop('recorded_camera_mount', 'off')
    # The original v142 controller config predates heading. Preserve its
    # omitted-option replay; new host bundles explicitly select the shared on.
    plain['options'].setdefault('heading_mode', 'off')
    factory = runtime_factory(plain)
    return lambda *args, **kw: recorded_camera(certify(guard(active(factory(*args, **kw), active_localization=a),
        active_rotation_guard=g), localization_certification=certification), recorded_camera_mount=mount)


class OwnPosePort:
    """Route a pair actor's own history through its existing S2 localizer once."""
    def __init__(self, localizer):
        self.localizer = localizer
        self.frame = None

    def __getattr__(self, name):
        return getattr(self.localizer.pose, name)

    def init_prior(self, *args, **kwargs):
        raise AssertionError('S3_START_PRIOR_FORBIDDEN')

    def on_command(self, row):
        if row['kind'] != 'initial_servo_command':
            self.localizer.on_command(self.localizer.robot_id, row['t'],
                                      {k: v for k, v in row.items() if k != 't'})

    def on_frame(self, now, rgb):
        if rgb is None:
            return self.localizer.pose.on_frame(now, None)
        obs, _ = self.frame
        if obs['robot_id'] != self.localizer.robot_id or abs(obs['sim_time']-now) > 1e-8:
            raise ValueError('foreign or stale pair localizer input')
        self.localizer.on_frames(now, {self.localizer.robot_id: (obs, rgb)})
        return self.localizer.last_report

    def close(self):
        pass  # Runtime owns and closes all three localizers exactly once.


class PairRuntime(old.pair.Runtime):
    def __init__(self, static, calibration, calibration_sha, *, seed, order, ports):
        from harness.zone_own_executor import ZoneOwnExecutor
        from harness.pair_passage_plan import executor_view
        from harness.zone_final_pair_guards import PairArmGuard
        from harness.pose_provider import is_own_pose_provider
        task = old.pair_task(static, order)
        planner = bind(old.skill.make_plan, task=lambda _: task)
        planner(static, task['sheet'], task['target'])

        class SlotTeam(old.pair.Team):
            _carry_yaw_record = carry_yaw_record

            def __init__(self, *args):
                super().__init__(*args)
                self.start = MethodType(bind(self.start.__func__, make_plan=planner), self)

        def initialize_pair(instance, static, calibration_path, calibration_sha, *, seed, provider_factory=None):
            instance.actors, instance.providers, instance.submitted = {}, dict(ports), set()
            instance.task, instance.started = task, False
            for i, rid in enumerate(('r1', 'r2')):
                provider = ports[rid]
                actor = ZoneOwnExecutor.__new__(ZoneOwnExecutor)
                # Admit this explicit own-history adapter only around an already
                # registered provider; keep the shared executor registry frozen.
                initialize_actor = bind(ZoneOwnExecutor.__init__, is_own_pose_provider=lambda p:
                    type(p) is OwnPosePort and is_own_pose_provider(p.localizer.pose))
                initialize_actor(actor, rid, executor_view(static),
                    provider.provider.calibration['params'], task['order'], skill_factory=None,
                    pose_estimate_cls=None, search_rows_y=(), pose_source=provider,
                    job_sim_limit_s=120., seed=seed+i, judgments=False)
                instance.actors[rid] = actor
                instance.actors[rid].guard = PairArmGuard(static)
            instance.team = SlotTeam(instance.actors, ports['r1'].provider.calibration, task)

        initialize_pair(self, static, calibration, calibration_sha, seed=seed)
        from harness.zone_pair_highpose_contract import CASE_CAP_S
        self.job_sim_limit_s = CASE_CAP_S
        for actor in self.actors.values():
            actor.job_sim_limit_s = CASE_CAP_S
        self.own_image_gates = old.pair.adopt_v98_frame_gate(self)
        self.look_recovery = old.pair.adopt_look_recovery(self)


class IntegratedTrial(old.IntegratedTrial):
    def __init__(self, *args, **kwargs):
        bind(old.IntegratedTrial.__init__, public_tasks=public_tasks)(self, *args, **kwargs)


class Runtime(door.Runtime):
    def __init__(self, static, orders, calibration, calibration_sha, *, seed, config):
        tasks = public_tasks(orders)
        make = solo_factory(config)
        self.localizers, self.boot_done, self.boot_records = {}, set(), {}
        self.boot_finished_at = None
        self.pair = self.solo = None
        self.trial, self.started = None, False
        self.event_offsets = {'r1': 0, 'r2': 0}
        self.door_failure = None
        try:
            for i, rid in enumerate(ROBOTS):
                self.localizers[rid] = make(static, calibration, calibration_sha, seed=seed+i,
                    robot_id=rid, pickup_slot=tasks['cyan']['initial_location']['slot'], destination='B')
            self.pose_ports = {r: OwnPosePort(self.localizers[r]) for r in ('r1', 'r2')}
            self.pair = PairRuntime(static, calibration, calibration_sha, seed=seed,
                order=tasks['long_beam'], ports=self.pose_ports)
            self.solo = self.localizers['r3']
            submit = self.pair.team.start
            self.links = {r: old.OwnLink(r, self.pair, tasks['long_beam'], submit=submit) for r in ('r1', 'r2')}
            self.links['r3'] = old.OwnLink('r3', self.solo, tasks['cyan'])
            self.pair.team.start = self._pair_claim
            from sim.zone_model_conventions import station_offset
            passage = next(p for p in static['passages'] if p['id'] == 'door_1')
            end_x = passage['center_m'][0]+passage['half_extents_m'][0]
            self.clients = {}
            for rid, actor in self.pair.actors.items():
                role = next(k for k, r in old.ROLES.items() if r == rid)
                self.clients[rid] = door.Client(rid, own_report=lambda a=actor: a.last_report,
                    own_done=lambda a=actor: any(j['kind'] == 'pair_carry' and j.get('confirmation') != 'failed'
                                                for j in a.jobs_done),
                    door_exit_x=end_x, offset=station_offset(static, 'long_beam', role),
                    envelope=tuple(max(abs(v) for v in old.skill.ENVELOPE[k]) for k in ('x_m', 'y_m')))
            solo = self.solo
            self.clients['r3'] = door.Client('r3', own_report=lambda: solo.last_report,
                own_done=lambda: solo.terminal and not solo.failure, door_exit_x=end_x,
                offset=(0., 0., 0.),
                envelope=tuple(max(abs(v) for v in old.solo.ENVELOPE[k]) for k in ('x_m', 'y_m')))
            self.relay = door.Relay()
            self.pair = door.GatedProducer(self.pair, ('r1', 'r2'), self.clients)
            self.solo = door.GatedProducer(self.solo, ('r3',), self.clients)
            self.wait_robot_s = {r: 0. for r in ROBOTS}
            self.last_tick, self.waiting, self.wait_accounted_until = None, set(ROBOTS), None
        except Exception:
            self.close()
            raise

    def initial_commands(self, now, commands):
        for rid, own in self.localizers.items():
            own.initial_commands(now, {rid: copy.deepcopy(commands[rid])})
        self.pair.initial_commands(now, {r: copy.deepcopy(commands[r]) for r in ('r1', 'r2')})

    def on_frames(self, now, frames):
        if set(frames) != set(ROBOTS):
            raise ValueError('three isolated own frames required')
        for rid in ROBOTS:
            self.links[rid].observe(now, frames[rid])
        for rid, port in self.pose_ports.items():
            port.frame = frames[rid]
        if self.boot_finished_at is None:
            for rid, own in self.localizers.items():
                own.on_frames(now, {rid: frames[rid]})
        else:
            if not self.pair_ended:
                self.pair.on_frames(now, {r: frames[r] for r in ('r1', 'r2')})
            if not self.solo.terminal:
                self.solo.on_frames(now, {'r3': frames['r3']})

    @property
    def failures(self):
        rows = super().failures
        rows.update({r: own.failure for r, own in self.localizers.items() if own.failure})
        return rows

    def step(self, now):
        if self.boot_finished_at is not None:
            return super().step(now)
        if self.failures:
            return [(r, {'kind': 'hold'}) for r in ROBOTS]
        rows = []
        for rid, own in self.localizers.items():
            actions = own.step(now) if rid not in self.boot_done else [(rid, {'kind': 'hold'})]
            moving = any(a['kind'] in ('drive', 'mecanum') and
                         any(a.get(k, 0) for k in ('forward', 'left', 'turn')) for _, a in actions)
            if rid not in self.boot_done and (moving or own.state not in ('init', 'scan', 'search_move')):
                # Same boundary as S2 start_only_class: first navigation pulse
                # is NOT issued. Keep the acquired own posterior and arm history.
                self.boot_done.add(rid)
                self.boot_records[rid] = dict(t=now, first_motion_withheld=True,
                    state=own.state, prior=copy.deepcopy(own.pose.provider.prior))
                actions = [(rid, {'kind': 'hold'})]
            rows.extend(actions)
        if set(self.boot_done) == set(ROBOTS):
            self.boot_finished_at = now
        return [(r, {'kind': 'hold'}) for r in ROBOTS] if self.failures else rows

    def on_command(self, rid, now, action):
        if self.boot_finished_at is None:
            # Initial observation is outside the door critical section. Count
            # its own commands, but never inflate reservation wait time with it.
            return old.Runtime.on_command(self, rid, now, action)
        return super().on_command(rid, now, action)

    def record(self):
        result = super().record()
        result.update(profile='s3-no-prior-mixed-v142', startup=self.boot_records,
            startup_finished_at=self.boot_finished_at, startup_pose_information=False,
            localizers={r: own.record() for r, own in self.localizers.items()},
            pair_v7_loaded_motion_qualified=False)
        return result

    def close(self):
        for own in self.localizers.values():
            own.close()
