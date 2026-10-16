"""Simulator-free two-actor scheduler: own pixels/commands, static task, enums.

The physics owner passes serialized inputs; this object never receives ports,
a world, seeded spawn rows, measured joints or evaluation results.
"""
from __future__ import annotations

import copy

from harness.zone_final_pair_contract import ROBOTS
from harness.zone_final_pair_guards import PairArmGuard
from harness.zone_final_pair_skill import Team, task


class Runtime:
    def __init__(self, static, calibration_path, calibration_sha, *, seed, provider_factory=None):
        from harness.vision_pose_source_pair_v3 import build_provider
        from harness.zone_own_executor import ZoneOwnExecutor
        from harness.pair_passage_plan import executor_view
        from sim.zone_model_conventions import spawn_layout
        self.actors, self.providers, self.submitted = {}, {}, set()
        self.task = task(static)
        self.started = False
        try:
            for i, rid in enumerate(ROBOTS):
                provider = (provider_factory or build_provider)(static, calibration_path, calibration_sha, seed+i)
                self.providers[rid] = provider
                # Public dock REGION only, never the seeded robot->row mapping.
                dock = spawn_layout(static)
                rows = dock['spawn_rows_y']
                provider.init_prior((dock['spawn_x'], sum(rows)/len(rows), 0.),
                                    (.15, max(.15, max(rows)-min(rows)), .174533),
                                    source='public static start dock region; row assignment unknown')
                self.actors[rid] = ZoneOwnExecutor(rid, executor_view(static), provider.provider.calibration['params'],
                    self.task['order'], skill_factory=None, pose_estimate_cls=None, search_rows_y=(), pose_source=provider,
                    job_sim_limit_s=120., seed=seed+i, judgments=False)
                self.actors[rid].guard = PairArmGuard(static)
            self.team = Team(self.actors, self.providers['r1'].provider.calibration, self.task)
        except Exception:
            self.close()
            raise

    def initial_commands(self, now, commands):
        for rid in ROBOTS:
            self.actors[rid].on_command({'t': now, 'kind': 'initial_servo_command',
                                        'pulses': copy.deepcopy(commands[rid])})

    def on_frames(self, now, frames):
        for rid in ROBOTS:
            obs, rgb = frames[rid]
            self.actors[rid].on_frame(now, obs, rgb)

    def on_command(self, rid, now, action):
        self.actors[rid].on_command({'t': now, **copy.deepcopy(action)})

    def step(self, now):
        if not self.started:
            for own in self.actors.values():
                own.look_around()
            self.started = True
        issued = []
        for rid, own in self.actors.items():
            if own.job is None and rid not in self.submitted:
                ack = self.team.start(rid, 'cargoX', self.task['target'], next(r for r in ROBOTS if r != rid), now=now)
                if ack['accepted']:
                    self.submitted.add(rid)
            decision = own.step(now)
            if decision['mode'] == 'capture':
                raise RuntimeError('fresh own frame required before control tick')
            if decision['mode'] != 'tick':
                raise RuntimeError('unexpected non-pair macro')
            issued.extend((rid, c) for c in decision['commands'])
        self.team.poll(now)
        return issued

    def arm_step(self, now):
        issued = []
        for rid, own in self.actors.items():
            if own._pair is not None:
                issued.extend((rid, c) for c in own._pair.arm_step(now))
        return issued

    def record(self):
        return {'pair': self.team.records(), 'robots': {rid: {
            'events': own.events, 'jobs': own.jobs_done, 'admissions': own.pair_admission_log,
            'provider': own.pose.record()} for rid, own in self.actors.items()}}

    def close(self):
        errors = []
        for provider in self.providers.values():
            try:
                provider.close()
            except Exception as exc:
                errors.append(str(exc))
        if errors:
            raise RuntimeError('; '.join(errors))
