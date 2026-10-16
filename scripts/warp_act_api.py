"""Default-off own-RGB ACT batch API, backed by the qualified warp3 controller.

Linux gcp2 only. No teacher object is constructed by this actor owner. Reset
supports new free-body starts within each world's exact static model; changing
geometry, mass, topology or camera requires a new owner and exact references.
"""
from __future__ import annotations

import base64
from collections import deque
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import platform
import subprocess
import sys

QUALIFIED = 'f0db6b1abb842ea65b71c433738210254f300a7c'
GATE_RAW_SHA = 'a7f0a28cf927f718245c4c1c31bcf4cc760ad5526be5ff62bfe4a5727bd329be'
TEACHER = '6f057f7e97c1a3aec9e8c398b8d9068e27b25df8'
# Native mjSTATE_INTEGRATION plus documented persistent history/sleep state.
# Compact solver values are derived again at the next step; replay checks that
# restoring these owners also preserves the untouched world's NEXT dynamics.
STATE = ('qpos', 'qvel', 'act', 'history', 'ctrl', 'qacc_warmstart',
         'qfrc_applied', 'xfrc_applied', 'mocap_pos', 'mocap_quat',
         'eq_active', 'time', 'tree_asleep', 'tree_awake',
         'ntree_awake', 'nbody_awake', 'nv_awake', 'cqacc_warmstart')


def admit(qualification, qualified_source, teacher_source):
    if platform.system() != 'Linux':
        raise RuntimeError('Mac physics/render forbidden; Linux gcp2 only')
    for source, sha in ((qualified_source, QUALIFIED), (teacher_source, TEACHER)):
        if subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip() != sha:
            raise ValueError('exact qualified source required')
        if subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain', '--untracked-files=no']):
            raise ValueError('qualified source must be clean')
    q = json.loads(Path(qualification).read_text())
    raw_path = Path(q['raw']['original'])
    raw = raw_path.read_bytes() if raw_path.exists() else subprocess.check_output(['zstd', '-dc', q['raw']['archive']])
    if hashlib.sha256(raw).hexdigest() != GATE_RAW_SHA:
        raise ValueError('unverified gate ledger')
    gate = json.loads(raw)
    if gate['source_sha'] != QUALIFIED or not gate['passed'] or gate['N'] != 40 or gate['n'] < 38:
        raise ValueError('qualified MJWarp gate required')
    return gate


class History:
    """ACT15 OwnHistory semantics, independent of simulator/evaluator imports."""
    def __init__(self, contract, episode, initial):
        self.c, self.episode = contract, episode
        self.issued = deque([deepcopy(contract.command(initial)) for _ in range(contract.HISTORY)], maxlen=contract.HISTORY)
        self.frames, self.clock, self.index = deque(), contract.IssuedClock(), 0

    def observe(self, now, jpeg, plan, skill):
        c = self.c
        ref = dict(path=f'rgb/r1/{self.index:06d}.jpg', sha256=hashlib.sha256(jpeg).hexdigest(), t=now, robot_id='r1')
        self.frames.append((ref, jpeg))
        while len(self.frames) > 1 and self.frames[1][0]['t'] < now-c.MEMORY_S-.1:
            self.frames.popleft()
        refs = c.image_history([r for r, _ in self.frames], now)
        pixels = {r['path']: jpg for r, jpg in self.frames}
        destination = 'pickup_site' if skill == 'release' else 'none'
        obs = dict(schema=c.SCHEMA, robot_id='r1', sample_id=f'{self.episode}:{self.index}:r1', t=now,
                   skill=skill, object_kind=plan['kind'], role=plan['role'], destination_zone=destination,
                   rgb=refs, issued=deepcopy(list(self.issued)),
                   **self.clock.observe((skill, plan['kind'], plan['role'], destination), now, self.issued[-1]['pwm']))
        c.validate_observation(obs)
        self.index += 1
        return obs, tuple(pixels[r['path']] for r in refs)

    def issue(self, command):
        self.issued.append(deepcopy(self.c.command(command)))


class Owner:
    def __init__(self, plans, out, *, qualified_source, teacher_source, qualification,
                 references, compiled_reference, compiled_geometry, enabled=False, training=False, audit_state=False):
        if not enabled:
            raise ValueError('MJWarp actor API is default OFF')
        gate = admit(qualification, qualified_source, teacher_source)
        sys.path.insert(0, str(Path(qualified_source)/'scripts'))
        from simalt_host import gcp2_identity
        self.host = gcp2_identity()
        if self.host != gate['cohort']['host']:
            raise ValueError('actor API requires the qualified gcp2 host')
        sys.path.insert(0, str(teacher_source))
        import sim
        sim.__path__.append(str(Path(qualified_source)/'sim'))
        import numpy as np
        import mujoco
        from harness import grasp_act_contract as c
        from warp_act_backend import WarpTransport
        self.np, self.mj, self.c = np, mujoco, c
        self.out = Path(out); self.out.mkdir(parents=True, exist_ok=False)
        self.plans, self.n, self.training = deepcopy(plans), len(plans), training
        self.audit_state = audit_state
        if not 1 <= self.n <= 256:
            raise ValueError('one to256 worlds required')
        self.contexts, self.generations = [], [0]*self.n
        self.active, self.ages = np.ones(self.n, bool), np.zeros(self.n, int)
        self.skills = ['grasp']*self.n
        self.current, self.histories, self.previous = [None]*self.n, [None]*self.n, [None]*self.n
        self.rings = [deque(maxlen=100) for _ in plans]  # existing10Hz/10SIMs recording-only rule
        self.log = (self.out/'evaluation-only.jsonl').open('x')

        class ActorTransport(WarpTransport):
            def sync_render(h, contexts):
                # Reuse exact qualified renderer/JPEG; direct GPU transforms
                # avoid native ray/kinematics. No teacher visibility client.
                old = h.numpy_teacher_v1 if hasattr(h, 'numpy_teacher_v1') else False
                h.numpy_teacher_v1 = True
                class NoVisibility:
                    def update(self, transforms):
                        pass
                previous = getattr(h, 'visibility', None)
                h.visibility = NoVisibility()
                try:
                    return super().sync_render(contexts)
                finally:
                    h.numpy_teacher_v1 = old
                    h.visibility = previous

        self.hooks = ActorTransport(self.host, QUALIFIED, 'mjwarp_batch_v1', self.out,
                                   native_sleep_policy_compat_v1=True)
        self.hooks.scene_v5_v1 = self.hooks.batch_sleep_v1 = True
        self.hooks.numpy_teacher_v1 = False
        for i, plan in enumerate(plans):
            self.contexts.append(self.context(plan, i, self.out/f'world-{i:03d}'))
        self.hooks.initialize(self.contexts, compiled_reference=Path(compiled_reference),
                              compiled_geometry=Path(compiled_geometry), per_world_model_references=references)
        self.origin, self.tick = self.hooks.origin, 0
        self.keys = [self.model_key(x) for x in self.contexts]
        for i in range(self.n):
            self.bootstrap(i)
            self.measure(i, False)
        self.write('RUN_META.json', dict(backend='mjwarp_batch_v1', controller_source=QUALIFIED,
                   gate_raw_sha256=GATE_RAW_SHA, host=self.host, camera=self.hooks.camera,
                   teacher_constructed=False, training=training, weld='off', reset_scope='new free-body starts; fixed static model'))
        self.audit()

    def write(self, name, value):
        (self.out/name).write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')

    def context(self, plan, index, folder):
        from warp_act_scene import make_scene
        from sim.masterpi_drive_friction_v7 import build_world, PROFILE
        from sim.s2_realism_camera_binding import bind_camera
        from sim.grasp_act_port import DutyActPort
        if plan['kind'] not in ('cyan', 'red', 'green', 'yellow') or plan['robot_id'] != 'r1':
            raise ValueError('qualified solo r1 boxes only')
        scene = make_scene({**plan, 'end_color_scene': 'off'})
        scene.config['setup_only']['spawns'].update(plan['spawns'])
        world, scene = self.hooks.make_world(plan, scene, build_world, bind_camera, drive_profile=PROFILE,
            seed=plan['seed'], width=640, height=480, render=False, warehouse_layout=scene.engine_layout,
            warehouse_cargo_ids=None, roller_collision='mesh', idle_robot_contacts='off')
        name = scene.config['setup_only']['objects'][plan['item_id']]['body_name']
        body = world.model.body(name).id
        gids = [g for g in range(world.model.ngeom) if world.model.geom_bodyid[g] == body and world.model.geom_contype[g]]
        fingers = {world.model.geom('r1__'+s+'_finger').id: j for j, s in enumerate(('left', 'right'))}
        folder.mkdir(parents=True, exist_ok=False)
        (folder/'scene.xml').write_text(world.scene_xml)
        (folder/'plan.json').write_text(json.dumps(plan, indent=2)+'\n')
        from sim.grasp_act_solo_evaluation import Score
        return dict(world=world, port=DutyActPort(world, 'r1', allow_reverse=True, allow_mecanum=True),
                    gids=gids, finger_ids=fingers, folder=folder, body=body, score=Score(),
                    initial_xy=world.data.xpos[body, :2].copy(), last_eval=None, last_pos=None)

    def model_key(self, ctx):
        from warp_act_core import model_key
        return model_key(ctx['world'].scene_xml)

    def bootstrap(self, i):
        now = self.origin+self.tick*.1
        p = self.contexts[i]['port']
        p._servo_tick_time = now
        initial = dict(t=now, wheels=[0.]*4, duration_s=[0.]*4,
                       pwm={str(s): int(p._servo_pulses[s]) for s in self.c.SERVOS})
        self.previous[i] = initial
        self.histories[i] = History(self.c, f'warp3-{self.plans[i]["seed"]}-{i}-g{self.generations[i]}', initial)
        self.refresh(i)

    def refresh(self, i):
        jpeg = self.hooks.rgb[i]
        now = self.origin+self.tick*.1
        self.current[i] = self.histories[i].observe(now, jpeg, self.plans[i], self.skills[i])
        self.rings[i].append((int(self.ages[i]), jpeg))
        if self.ages[i] % 5 == 0:
            folder = self.contexts[i]['folder']/'review-own'; folder.mkdir(exist_ok=True)
            (folder/f'{int(self.ages[i]):06d}.jpg').write_bytes(jpeg)
        if not self.training: self.hooks.record_state(i, self.tick, self.contexts[i]['world'])

    def read_actor(self, i):
        # Reading is pure: it must not advance RGB/issued history.
        obs, jpgs = self.current[i]
        self.c.validate_observation(obs)
        return deepcopy(obs), tuple(jpgs)

    def read_training(self, i):
        if not self.training:
            raise RuntimeError('privileged lane unavailable in student evaluation')
        ctx = self.contexts[i]; d = ctx['world'].data
        # Explicitly separate training-only critic lane. Never attached to
        # read_actor, observation JSON, labels or public terminal flags.
        base = ctx['world'].robot('r1').base_xyz()
        rot = d.xmat[ctx['body']].reshape(3, 3)
        yaw = ctx['world'].robot('r1').base_rpy()[2]
        angle = math.atan2(rot[1, 0], rot[0, 0])-yaw
        truth = dict(distance_m=float(self.np.linalg.norm(d.xpos[ctx['body'], :2]-base[:2])),
                     alignment_rad=math.atan2(math.sin(angle), math.cos(angle)), target_xy=None,
                     stable_lift=bool(ctx['score'].lift_ok))
        return truth, tuple(d.qpos.tolist()+d.qvel.tolist()+self.hooks.contact_forces[i].tolist())

    def instruct(self, i, skill):
        if skill not in self.c.SKILLS or not 0 <= i < self.n or not self.active[i]:
            raise ValueError('active world and named ACT skill required')
        self.skills[i] = skill
        obs, jpgs = self.current[i]
        obs = deepcopy(obs); obs['skill'] = skill
        obs['destination_zone'] = 'pickup_site' if skill == 'release' else 'none'
        obs.update(self.histories[i].clock.observe((skill, self.plans[i]['kind'], self.plans[i]['role'], obs['destination_zone']), obs['t'], obs['issued'][-1]['pwm']))
        self.c.validate_observation(obs); self.current[i] = obs, jpgs

    def measure(self, i, issued_done):
        from sim.grasp_act_solo_evaluation import bottom_z
        np, ctx = self.np, self.contexts[i]
        m, d = ctx['world'].model, ctx['world'].data
        pos = d.xpos[ctx['body']].copy(); rot = d.xmat[ctx['body']].reshape(3, 3)
        now = self.origin+self.tick*.1
        speed = 0. if ctx['last_eval'] is None else float(np.linalg.norm(pos-ctx['last_pos'])/(now-ctx['last_eval']))
        row = dict(min_z=min(float(bottom_z('box', d.geom_xpos[g], d.geom_xmat[g].reshape(3, 3), m.geom_size[g])) for g in ctx['gids']),
            support_z=0., tilt_deg=math.degrees(math.acos(float(np.clip(rot[2, 2], -1., 1.)))),
            finger_forces=self.hooks.contact_forces[i].tolist(), speed=speed,
            open_issued=self.previous[i]['pwm']['1'] >= 1900,  # exact qualified teacher evaluator convention
            placement_offset=float(np.linalg.norm(pos[:2]-ctx['initial_xy'])), weld_active=bool(d.eq_active.any()))
        ctx['score'].add(now, **row)
        ctx['last_eval'], ctx['last_pos'] = now, pos
        record = dict(world=i, seed=self.plans[i]['seed'], generation=self.generations[i],
            t=now, elapsed_sim_s=int(self.ages[i])*.1, **row, **ctx['score'].record(issued_done))
        self.log.write(json.dumps(record, allow_nan=False)+'\n'); self.log.flush()
        return record

    def integration(self):
        h = self.hooks
        return {name: getattr(h.wd, name).numpy().copy() for name in STATE
                if hasattr(h.wd, name) and hasattr(getattr(h.wd, name), 'numpy')}

    def audit(self):
        if not self.audit_state: return
        # Private probe-only files, NEVER part of the actor RPC response.
        self.np.savez_compressed(self.out/'state-latest.npz', **self.integration(),
            relay=self.hooks.relay_state, ages=self.ages)
        ports = [{k: v for k, v in vars(c['port']).items() if k.startswith('_') and not hasattr(v, 'model')}
                 for c in self.contexts]
        self.write('ports-latest.json', ports)

    def restore(self, snapshot, indices):
        h = self.hooks
        for name, before in snapshot.items():
            if not before.size:
                continue
            target = getattr(h.wd, name)
            values = target.numpy(); values[indices] = before[indices]
            h.wp.copy(target, h.wp.array(values, dtype=target.dtype))

    def reset(self, plans, indices=None):
        np, h = self.np, self.hooks
        indices = list(range(self.n)) if indices is None else list(indices)
        if not indices or len(plans) != len(indices) or len(set(indices)) != len(indices) or any(type(i) is not int or not 0 <= i < self.n for i in indices):
            raise ValueError('one plan per unique world index required')
        # Validate EVERY replacement before changing physics or an actor cache.
        # Administrative rejected-attempt files are retained separately.
        proposed = []
        attempt = getattr(self, 'reset_attempt', 0)+1; self.reset_attempt = attempt
        cache_before = set(h.prototypes)
        try:
            for i, plan in zip(indices, plans):
                ctx = self.context(plan, i, self.out/f'reset-attempt-{attempt:04d}-world-{i:03d}')
                proposed.append(ctx)
                if self.model_key(ctx) != self.keys[i]:
                    raise ValueError('reset static model differs: create a new owner with exact references')
        except BaseException:
            for key in set(h.prototypes)-cache_before:
                h.prototypes.pop(key)[0].close()
            self.write(f'reset-rejection-{attempt:04d}.json', dict(category='incompatible_reset',
                blocking_object='static_model', minimum_gap_m=None,
                minimum_gap_status='not applicable: model compatibility, not geometric obstruction',
                reason='replacement batch rejected before any physics/history mutation'))
            raise
        before = self.integration()
        untouched = [i for i in range(self.n) if i not in indices]
        old_rgb = list(h.rgb); old_forces = h.contact_forces.copy()
        now = self.origin+self.tick*.1
        for i, plan, ctx in zip(indices, plans, proposed):
            self.save_ring(i)
            self.save_states(i)
            (self.contexts[i]['folder']/'reset-end.json').write_text(json.dumps(dict(status='cap_end',
                category='caller_reset', blocking_object='not_applicable', minimum_gap_m=None,
                reason='explicit reset before next generation; not a completed student success'))+'\n')
            # Fixed model already has exact C312 compatibility applied. Only
            # the fresh native setup's free-body integration state is new.
            ctx['world'].model = self.contexts[i]['world'].model
            for ctrl in ctx['world'].controllers.values():
                ctrl.model = ctx['world'].model
            self.contexts[i] = ctx
            self.plans[i] = deepcopy(plan)
        mask = np.zeros(self.n, bool); mask[indices] = True
        h.mjw.reset_data(h.wm, h.wd, h.wp.array(mask, dtype=bool))
        for name in STATE:
            target = getattr(h.wd, name, None)
            if target is None or not hasattr(target, 'numpy'):
                continue
            values = target.numpy()
            if not values.size:
                continue
            for i in indices:
                data = self.contexts[i]['world'].data
                if name == 'time': value = now
                elif name == 'tree_awake': value = (data.tree_asleep < 0).astype(np.int32)
                elif not hasattr(data, name): value = values[i]  # reset_data owns derived compact buffers
                else: value = getattr(data, name)
                values[i] = value
            h.wp.copy(target, h.wp.array(values, dtype=target.dtype))
        # The public reset API clears a shared contact counter. Restore every
        # untouched integration owner; derived contacts rebuild at next step.
        self.restore(before, untouched)
        h.relay_state[indices] = 0
        h.sync_render(self.contexts)
        for i in untouched:
            self.contexts[i]['world'].data.time = float(before['time'][i])
            h.rgb[i] = old_rgb[i]
            h.contact_forces[i] = old_forces[i]
        after = self.integration()
        equal = {k: bool(np.array_equal(v[untouched], after[k][untouched])) for k, v in before.items()}
        if not all(equal.values()):
            raise RuntimeError('partial reset changed untouched integration owners')
        for i in indices:
            self.generations[i] += 1; self.ages[i] = 0; self.active[i] = True
            self.skills[i] = 'grasp'
            self.rings[i].clear(); self.bootstrap(i)
            self.measure(i, False)
        keep = {hashlib.sha256(json.dumps(p, sort_keys=True).encode()).hexdigest() for p in self.plans}
        for key in set(h.prototypes)-keep:
            h.prototypes.pop(key)[0].close()
        self.write(f'reset-audit-{attempt:04d}.json', dict(indices=indices, untouched=untouched,
                   integration_equal=equal, scope='immediate isolation; paired next-step test required separately'))
        self.audit()
        return [self.read_actor(i) for i in range(self.n)]

    def step(self, actions):
        if len(actions) != self.n:
            raise ValueError('one action per world required')
        now = self.origin+self.tick*.1
        for i, action in enumerate(actions):
            if set(action) != {'command', 'done'} or type(action['done']) is not bool:
                raise ValueError('action whitelist mismatch')
            self.c.command(action['command'])
            # Existing ACT15 issued-clock validation tolerance, not a new
            # physical acceptance threshold.
            if self.active[i] and abs(action['command']['t']-now) > 1e-5:
                raise ValueError('issued clock mismatch')
        if not self.active.any():
            return [True]*self.n
        h, np = self.hooks, self.np
        inactive = np.flatnonzero(~self.active).tolist()
        frozen = self.integration() if inactive else None
        frozen_ports = {i: deepcopy({k: v for k, v in vars(self.contexts[i]['port']).items()
                                    if k.startswith('_') and not k.endswith('lock') and not hasattr(v, 'model')})
                        for i in inactive}
        old_rgb = list(h.rgb); old_relay = h.relay_state.copy()
        old_controller = {i: deepcopy(self.contexts[i]['world'].robot('r1').servo_command_pulses) for i in inactive}
        old_ctrl = {i: self.contexts[i]['world'].data.ctrl.copy() for i in inactive}
        for i, action in enumerate(actions):
            if not self.active[i]: continue
            cmd, p = action['command'], self.contexts[i]['port']
            p.apply(dict(kind='wheel_pulse', wheels=cmd['wheels'], duration_s=cmd['duration_s']), now)
            for servo, pulse in cmd['pwm'].items():
                s = int(servo)
                if pulse != self.previous[i]['pwm'][servo]:
                    p.apply(dict(kind='look', pan_pulse=pulse) if s == 6 else dict(kind='arm', servo_id=s, pulse=pulse), now)
            self.histories[i].issue(cmd); self.previous[i] = deepcopy(cmd)
        h.step(self.contexts, self.active); self.tick += 1
        if inactive:
            self.restore(frozen, inactive)
            h.relay_state[inactive] = old_relay[inactive]
            for i, state in frozen_ports.items():
                for k, v in state.items(): setattr(self.contexts[i]['port'], k, v)
            h.sync_render(self.contexts)
            for i in inactive:
                self.contexts[i]['world'].data.time = float(frozen['time'][i])
                self.contexts[i]['world'].data.ctrl[:] = old_ctrl[i]
                self.contexts[i]['world'].robot('r1').servo_command_pulses = old_controller[i]
                h.rgb[i] = old_rgb[i]
        for i, action in enumerate(actions):
            if not self.active[i]: continue
            self.ages[i] += 1
            self.refresh(i)
            evaluation = self.measure(i, action['done'])
            # Existing ACT full episode90SIMs, independent of task truth.
            cap = self.ages[i] >= 900
            self.active[i] = not (action['done'] or cap)
            self.log.write(json.dumps(dict(world=i, generation=self.generations[i], t=now+.1,
                issued_done=action['done'], cap_end=bool(cap), terminal=bool(not self.active[i])))+'\n')
            if not self.active[i]:
                self.save_ring(i)
                (self.contexts[i]['folder']/'result.json').write_text(json.dumps(dict(status='cap_end' if cap else 'complete', cap_end=bool(cap), issued_done=action['done'], evaluation=evaluation), indent=2)+'\n')
        self.log.flush()
        self.audit()
        return (~self.active).tolist()

    def save_ring(self, i):
        folder = self.contexts[i]['folder']/'last10s'; folder.mkdir(exist_ok=True)
        for tick, jpeg in self.rings[i]:
            (folder/f'{tick:06d}.jpg').write_bytes(jpeg)

    def close(self):
        for i in range(self.n): self.save_ring(i); self.save_states(i)
        self.log.close(); self.hooks.close()

    def save_states(self, i):
        samples = self.hooks.samples.get(i, [])
        if samples:
            self.np.savez_compressed(self.contexts[i]['folder']/'states.npz', ticks=[s[0] for s in samples],
                qpos=[s[1] for s in samples], qvel=[s[2] for s in samples])
            self.hooks.samples[i] = []
