"""P5 runner side of the learned pair-carry student evaluation (default OFF).

The student policy runs in an isolated actor process from the pairact student
tree (``dsh/pairact-p5-student`` ``scripts/pairact_r1_student_worker.py``).
This module only

* sends each robot's OWN camera JPEG and the command the runner actually
  applied (``WorkerClient``),
* runs the existing boolean READY -> GO -> ACK protocol
  (``harness.grasp_act_start_sync.GraspStartSync``) with the beamact4
  re-arming rule (a withdrawn READY rebuilds the barrier), and
* keeps an evaluation-only funnel from GT rows that never reach the student.

Nothing here constructs or steps a teacher, and no GT value is sent to the
worker (the request carries only ``jpeg`` and ``issued`` per robot).
"""
from __future__ import annotations

import base64
import json
import math
import subprocess
from pathlib import Path

MODE = 'pairact_r1_student_eval_v1'
CONFIG_KEYS = {'mode', 'python', 'source', 'model', 'config', 'device'}
FUNNEL = ('approach', 'alignment', 'READY', 'grasp', 'hold_3s', 'carry_1m', 'door', 'place')
# Evaluation-only geometry diagnostics, same constants as the CPU pair student
# runner (scripts/run_beamact2_student.py): pinned teacher STATION_M .203,
# XY_TOL .03, YAW_TOL .06, visible local hand-off envelope .8 m.
STATION_M, XY_TOL, YAW_TOL, APPROACH_M = .203, .03, .06, .8


def validate_config(cfg):
    if not isinstance(cfg, dict) or set(cfg) != CONFIG_KEYS or cfg['mode'] != MODE:
        raise ValueError('student eval config must be exactly ' + str(sorted(CONFIG_KEYS)))
    return cfg


class WorkerClient:
    """JSON-lines client of the isolated student worker process."""

    def __init__(self, cfg, *, popen=subprocess.Popen):
        cfg = validate_config(cfg)
        self.proc = popen([cfg['python'], '-m', 'scripts.pairact_r1_student_worker', '--model', cfg['model'],
                           '--config', cfg['config'], '--device', cfg['device']],
                          cwd=cfg['source'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
        hello = self._read()
        if hello != {'ready': True, 'mode': MODE}:
            raise RuntimeError(f'student worker startup mismatch: {hello}')

    def _read(self):
        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError('student worker exited')
        return json.loads(line)

    def request(self, payload):
        self.proc.stdin.write(json.dumps(payload, allow_nan=False) + '\n')
        self.proc.stdin.flush()
        return self._read()

    def flush(self):
        """Runner stream protocol (flushed with the log streams; nothing buffered here)."""

    def close(self):
        if self.proc.poll() is not None:
            return
        try:
            self.proc.stdin.close()
        finally:
            self.proc.wait(timeout=30)


class RearmingSync:
    """beamact4 RearmingStartSync rule over the pinned GraspStartSync factory."""

    def __init__(self, participants, delays, factory):
        self.participants, self.delays, self.factory = tuple(participants), dict(delays), factory
        self.sync = factory(self.participants, self.delays)
        self.previous = {r: False for r in self.participants}
        self.events, self.offset, self.cycle = [], 0, 0

    def tick(self, ready, now):
        if set(ready) != set(self.participants) or any(type(v) is not bool for v in ready.values()):
            raise ValueError('READY messages only')
        if any(self.previous[r] and not ready[r] for r in ready):
            self.cycle += 1
            self.events.append({'t': now, 'event': 'READY_withdrawn_rearm', 'cycle': self.cycle})
            self.sync = self.factory(self.participants, self.delays)
            self.offset = 0
        permits = self.sync.tick(ready, now)
        self.events.extend(dict(e, cycle=self.cycle) for e in self.sync.events[self.offset:])
        self.offset = len(self.sync.events)
        self.previous = dict(ready)
        return permits


class StudentEpisode:
    """One tick = propose (own inputs) -> protocol permits -> issue."""

    def __init__(self, client, roles, episode_id, initial, sync):
        self.client, self.roles, self.sync = client, dict(roles), sync
        self.finished = False
        self.ready = {r: False for r in roles}
        self.requests = 0
        reply = client.request({'op': 'reset', 'roles': self.roles, 'episode_id': episode_id,
                                'initial': {r: initial[r] for r in roles}})
        if reply != {'ok': True}:
            raise RuntimeError('student worker reset failed')

    def tick(self, now, jpegs, previous):
        if set(jpegs) != set(self.roles):
            raise ValueError('one own camera frame per robot')
        robots = {r: {'jpeg': base64.b64encode(jpegs[r]).decode(), 'issued': previous[r]} for r in self.roles}
        proposed = self.client.request({'op': 'propose', 't': float(now), 'robots': robots})['robots']
        self.ready = {r: bool(proposed[r]['ready']) for r in self.roles}
        permits = self.sync.tick(self.ready, now)
        issued = self.client.request({'op': 'issue', 't': float(now), 'permits': permits})
        self.requests += 2
        self.finished = bool(issued['finished'])
        return proposed, issued['robots']

    def summary(self):
        out = self.client.request({'op': 'summary'})
        out.update(protocol_events=self.sync.events, worker_requests=self.requests)
        return out


class StudentFunnel:
    """Evaluation only (GT rows): approach -> alignment -> READY -> grasp -> hold_3s.
    The carry part (carry_1m, door, place) comes from ``pair_carry_eval``."""

    def __init__(self):
        self.first = {}

    def add(self, now, truth, roles, ready, joint_held):
        geometry = {}
        for rid, role in roles.items():
            pose, end = truth['robots'][rid]['pose'], truth['beam']['ends'][role]
            yaw = truth['beam']['pose'][2] + (math.pi if role == 'blue' else 0.)
            goal = (end[0] - STATION_M*math.cos(yaw), end[1] - STATION_M*math.sin(yaw))
            geometry[rid] = (math.dist(pose[:2], end[:2]), math.dist(pose[:2], goal),
                             abs(math.atan2(math.sin(yaw - pose[2]), math.cos(yaw - pose[2]))))
        passed = {'approach': all(g[0] <= APPROACH_M for g in geometry.values()),
                  'alignment': all(g[1] <= XY_TOL and g[2] <= YAW_TOL for g in geometry.values()),
                  'READY': all(ready.values()),
                  'grasp': all(min(truth['contacts'][r]) >= .5 for r in roles),
                  'hold_3s': bool(joint_held)}
        for i, stage in enumerate(FUNNEL[:5]):
            if (i == 0 or FUNNEL[i-1] in self.first) and passed[stage]:
                self.first.setdefault(stage, now)
        return passed

    def record(self, carry_eval):
        reached = {s: s in self.first for s in FUNNEL[:5]}
        f = (carry_eval or {}).get('funnel') or {}
        chain = reached['hold_3s']
        reached['carry_1m'] = chain = bool(chain and f.get('carried_1m') and not (carry_eval or {}).get('drop_events'))
        reached['door'] = chain = bool(chain and f.get('door_passed'))
        reached['place'] = bool(chain and (carry_eval or {}).get('success'))
        return {'order': list(FUNNEL), 'reached': reached, 'first_pass_t': dict(self.first),
                'first_failure': next((s for s in FUNNEL if not reached[s]), None)}


def start(cfg, roles, episode_id, initial, *, seed, factory, client=None):
    """Runner glue: same RNG/delay construction as the beampair7 runner."""
    import numpy as np
    rng = np.random.default_rng(seed)
    delays = {r: (0. if k == 0 else float(rng.uniform(0, 1.5))) for k, r in enumerate(roles)}
    client = client or WorkerClient(cfg)
    return StudentEpisode(client, roles, episode_id, initial, RearmingSync(roles, delays, factory)), delays
