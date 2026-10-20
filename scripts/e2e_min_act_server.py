#!/usr/bin/env python3
"""E2E-min ACT actor server (torch env child of the nav runner; default off).

Reproduces the C2c policy side exactly as ``act18_evaluate.py`` configures it
(branch dsh/act18-c2c-v7clock, run source 257dcacc):

* actor: ``act18_policy.Actor.load(checkpoint, device='cuda')``
  (``act18_evaluate.py:273,414``; evaluate_act16w.py:45);
* ``contract.CHUNK = adapter.json['chunk']`` (``act18_evaluate.py:281``);
* executor: ``harness.grasp_act_policy.ChunkExecutor`` with
  ``n_action_steps=1, temporal_ensemble_coeff=.01`` (``act18_evaluate.py:315``);
  no done head, no loop overlay (C2c arms);
* one executor per robot, ``reset`` on a skill start (evaluate_act16w.py:68-69).

The v7 clock is applied by the client when it builds the observation
(harness/e2e_min_act.py), so this process never edits observations.

Protocol (JSON lines on stdin/stdout):
  -> {"op":"step","robot":"r1","observation":{...},"jpegs":[b64,...]}
  <- {"command":{...},"done":bool}
  -> {"op":"reset","robot":"r1"}   <- {"ok":true}
  -> {"op":"close"}                <- {"ok":true}
First line out: {"ready":true, ...receipt}.  Any error -> {"error":...} and exit 1.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROBOTS = ('r1', 'r2')
C2C_EXECUTOR = dict(n_action_steps=1, temporal_ensemble_coeff=.01)


class ActServerCore:
    """Request handling without torch (unit-tested with a fake actor)."""

    def __init__(self, predict, executor_factory, contract):
        self.contract = contract
        self.executors = {r: executor_factory(predict) for r in ROBOTS}
        self.steps = {r: 0 for r in ROBOTS}

    def handle(self, request):
        op = request.get('op')
        if op == 'close' and set(request) == {'op'}:
            return dict(ok=True), True
        robot = request.get('robot')
        if robot not in ROBOTS:
            raise ValueError('robot r1/r2 required')
        if op == 'reset' and set(request) == {'op', 'robot'}:
            self.executors[robot].reset()
            return dict(ok=True), False
        if op == 'step' and set(request) == {'op', 'robot', 'observation', 'jpegs'}:
            obs = request['observation']
            self.contract.validate_observation(obs)
            if obs['robot_id'] != robot:
                raise ValueError('observation robot mismatch')
            jpegs = tuple(base64.b64decode(j) for j in request['jpegs'])
            if len(jpegs) != self.contract.RGB_HISTORY:
                raise ValueError('four own RGB lags required')
            command, done = self.executors[robot].step(obs, jpegs)
            self.steps[robot] += 1
            return dict(command=self.contract.command(command), done=bool(done)), False
        raise ValueError('request whitelist mismatch')


def serve(core, stdin, stdout):
    for line in stdin:
        reply, stop = core.handle(json.loads(line))
        stdout.write(json.dumps(reply, allow_nan=False) + '\n')
        stdout.flush()
        if stop:
            return


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--enabled', action='store_true')
    ap.add_argument('--act-source', type=Path, required=True,
                    help='clean clone of dsh/act18-c2c-v7clock at the C2c run source')
    ap.add_argument('--expected-act-sha', required=True)
    ap.add_argument('--checkpoint', type=Path, required=True)
    ap.add_argument('--expected-model-sha256', required=True)
    ap.add_argument('--device', default='cuda')
    a = ap.parse_args(argv)
    out = sys.stdout
    sys.stdout = sys.stderr          # keep library prints off the protocol
    try:
        if not a.enabled:
            raise ValueError('E2E ACT server is default OFF')
        head = subprocess.check_output(['git', '-C', str(a.act_source), 'rev-parse', 'HEAD'], text=True).strip()
        if head != a.expected_act_sha:
            raise ValueError('ACT source SHA mismatch: ' + head)
        if subprocess.check_output(['git', '-C', str(a.act_source), 'status', '--porcelain',
                                    '--untracked-files=no']):
            raise ValueError('ACT source must be clean')
        model = a.checkpoint / 'model.safetensors'
        digest = hashlib.sha256(model.read_bytes()).hexdigest()
        if digest != a.expected_model_sha256:
            raise ValueError('checkpoint sha256 mismatch')
        sys.path.insert(0, str(a.act_source / 'scripts'))
        sys.path.insert(0, str(a.act_source))
        from harness import grasp_act_contract as contract
        from harness.grasp_act_policy import ChunkExecutor
        from act18_policy import Actor
        meta = json.loads((a.checkpoint / 'adapter.json').read_text())
        contract.CHUNK = meta['chunk']
        actor = Actor.load(a.checkpoint, device=a.device)
        core = ActServerCore(actor.predict, lambda predict: ChunkExecutor(predict, **C2C_EXECUTOR), contract)
        receipt = dict(ready=True, act_source_sha=head, model_sha256=digest, chunk=meta['chunk'],
                       executor=C2C_EXECUTOR, done_head=False, loop_overlay=False,
                       clock='client-side v7 deadband 2', contract_sha256=hashlib.sha256(
                           (a.act_source / 'harness/grasp_act_contract.py').read_bytes()).hexdigest(),
                       device=a.device)
        out.write(json.dumps(receipt) + '\n'); out.flush()
        serve(core, sys.stdin, out)
        return 0
    except Exception as exc:  # report and fail closed
        out.write(json.dumps(dict(error=f'{type(exc).__name__}: {exc}')) + '\n'); out.flush()
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
