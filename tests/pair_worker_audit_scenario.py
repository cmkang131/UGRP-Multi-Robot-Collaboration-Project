"""Synthetic scenario for the opt-in pair-worker provenance audit.

The scenario drives the OWNED four-operation entry of the pinned geometry
worker with a FIXED SYNTHETIC predictor.  No learned model, no simulator, no
GPU, no robot and no head worker process are used: the predictor returns a
constant action chunk and a constant stage plan, so every run is byte
reproducible.

Two modes are supported:

``prepare``
    Copy the pinned worker harness into a scratch tree and drop the candidate
    audit module next to it.  The copy is byte identical to the pinned tree,
    so the candidate is audited against the pinned controller without
    touching the pinned tree.

``run``
    Run the owned entry against a prepared tree (audit ON or OFF) or against
    the pinned tree with a candidate from another harness tree (the
    fail-closed case).  The scenario prints one JSON object on stdout.

Usage::

    python tests/pair_worker_audit_scenario.py prepare \
        --pinned-root <tree> --candidate <file> --dest <dir>
    python tests/pair_worker_audit_scenario.py run \
        --student-root <tree> --geometry-worker <script> --audit on \
        --run-id <id> --output-root <dir> [--ticks 24]
"""
from __future__ import annotations

import argparse
import base64
import importlib.util
import json
from pathlib import Path
import shutil
import sys

ROLES = {'r1': 'teal', 'r2': 'blue'}
EPISODE_ID = 'ep-audit-001'
SERVO_PWM = {'1': 1500, '3': 1500, '4': 1500, '5': 1500, '6': 1500}
PERIOD_S = 0.1
# The first four ticks are held (no GO/ACK): the barrier must hold the last
# PWM with stopped wheels.  From tick four on the permit is granted.
PERMIT_FROM_TICK = 4

# Fixed synthetic stage plan per predictor call.  The first call walks
# approach -> ready -> execute so that the READY/GO-ACK hold branch and the
# real issue branch are both exercised; later calls stay in execute.
FIRST_STAGE_PLAN = ('approach', 'approach', 'ready', 'ready',
                    'execute', 'execute', 'carry', 'carry')
LATER_STAGE_PLAN = ('execute',) * 8
STAGE_INDEX = ('approach', 'alignment', 'ready', 'execute',
               'carry', 'place', 'recover', 'complete')


def synthetic_predict_factory():
    """A fixed synthetic predictor (no learned weights, no inference).

    The stage plan is counted PER ROBOT so that the two robots follow the
    same deterministic sequence; a shared counter would desynchronise them.
    """
    state = {'calls': {}}

    def predict(observation, jpegs):
        import numpy as np
        robot_id = observation['robot_id']
        index = state['calls'].get(robot_id, 0)
        state['calls'][robot_id] = index + 1
        plan = FIRST_STAGE_PLAN if index == 0 else LATER_STAGE_PLAN
        chunk = np.zeros((8, 14), dtype=float)
        chunk[:, 0:4] = 0.35          # wheels
        chunk[:, 4:8] = 1.0           # pulse widths -> 150 ms
        chunk[:, 8:13] = 0.0          # pwm offsets -> 1500
        chunk[:, 13] = 0.0            # done flag
        logits = np.zeros((8, 8), dtype=float)
        for row, stage in enumerate(plan):
            logits[row, STAGE_INDEX.index(stage)] = 1.0
        return {'chunk': chunk, 'stage_logits': logits}

    return predict


class Capture:
    """A minimal stdout sink that keeps every printed line."""

    def __init__(self):
        self.chunks = []

    def write(self, text):
        self.chunks.append(text)

    def flush(self):
        pass

    def lines(self):
        return [chunk for chunk in self.chunks if chunk.strip()]


def jpeg_for(robot_id, tick):
    return b'\xff\xd8\xff' + ('%s-%04d' % (robot_id, tick)).encode('ascii')


def initial_command():
    return {'t': 0.0, 'wheels': [0.0] * 4, 'duration_s': [0.0] * 4,
            'pwm': dict(SERVO_PWM)}


def prepare_tree(pinned_root, candidate, dest):
    """Copy the pinned harness into ``dest`` and add the candidate module."""
    dest = Path(dest)
    # Never delete an existing destination supplied to this helper.
    dest.mkdir(parents=True, exist_ok=False)
    ignore = shutil.ignore_patterns('__pycache__')
    shutil.copytree(Path(pinned_root) / 'harness', dest / 'harness', ignore=ignore)
    # The pinned harness package reads its action allowlist from
    # <tree>/scripts/robot_actions.py; the copy is byte identical.
    shutil.copytree(Path(pinned_root) / 'scripts', dest / 'scripts', ignore=ignore)
    shutil.copy2(candidate, dest / 'harness' / Path(candidate).name)
    return dest


def load_candidate(candidate):
    """Import the candidate audit module from an explicit file path."""
    spec = importlib.util.spec_from_file_location('ugrp_candidate_audit',
                                                  str(Path(candidate).resolve()))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_requests(ticks, capture):
    """The four-operation request stream; it reads the printed responses."""
    initial = {rid: initial_command() for rid in ROLES}
    yield json.dumps({'op': 'reset', 'roles': dict(ROLES), 'episode_id': EPISODE_ID,
                      'initial': initial})
    applied = {rid: initial[rid] for rid in ROLES}
    for tick in range(ticks):
        now = round(PERIOD_S * tick, 6)
        yield json.dumps({'op': 'propose', 't': now,
                          'robots': {rid: {'jpeg': base64.b64encode(jpeg_for(rid, tick)).decode('ascii'),
                                           'issued': applied[rid]} for rid in ROLES}})
        permit = tick >= PERMIT_FROM_TICK
        yield json.dumps({'op': 'issue', 't': now,
                          'permits': {rid: permit for rid in ROLES}})
        response = json.loads(capture.lines()[-1])
        applied = {rid: response['robots'][rid]['command'] for rid in ROLES}
    yield json.dumps({'op': 'summary'})


def run(args):
    capture = Capture()
    predict = synthetic_predict_factory()
    argv = ['--student-root', str(args.student_root),
            '--geometry-worker', str(args.geometry_worker)]
    if args.audit == 'on':
        argv += ['--audit-run-id', args.run_id,
                 '--audit-output-root', str(args.output_root)]
        if args.audit_sources is not None:
            argv += ['--audit-sources', str(args.audit_sources)]
    if args.candidate is not None:
        module = load_candidate(args.candidate)
    else:
        from harness import pair_worker_audit as module

    payload = {'audit': args.audit, 'ticks': args.ticks}
    try:
        module.owned_worker_main(argv, predict=predict, stdin=build_requests(args.ticks, capture),
                                 stdout=capture)
    except Exception as exc:                     # noqa: BLE001 - reported, not hidden
        payload['error_type'] = type(exc).__name__
        payload['error'] = str(exc)
        payload['stdout'] = [json.loads(line) for line in capture.lines()]
        print(json.dumps(payload, sort_keys=True))
        return 0
    payload['stdout'] = [json.loads(line) for line in capture.lines()]
    audit_file = None
    if args.audit == 'on':
        root = Path(args.output_root)
        files = sorted(root.glob('pair-audit-*.jsonl'))
        if len(files) != 1:
            raise SystemExit('expected exactly one audit file, found %d' % len(files))
        audit_file = files[0]
        payload['audit_file'] = str(audit_file)
        payload['audit_records'] = [json.loads(line)
                                    for line in audit_file.read_text(encoding='utf-8').splitlines()
                                    if line.strip()]
    print(json.dumps(payload, sort_keys=True))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prep = sub.add_parser('prepare')
    prep.add_argument('--pinned-root', type=Path, required=True)
    prep.add_argument('--candidate', type=Path, required=True)
    prep.add_argument('--dest', type=Path, required=True)
    run_parser = sub.add_parser('run')
    run_parser.add_argument('--student-root', type=Path, required=True)
    run_parser.add_argument('--geometry-worker', type=Path, required=True)
    run_parser.add_argument('--audit', choices=('on', 'off'), required=True)
    run_parser.add_argument('--run-id', default='scenario')
    run_parser.add_argument('--output-root', type=Path, default=None)
    run_parser.add_argument('--audit-sources', type=Path, default=None)
    run_parser.add_argument('--candidate', type=Path, default=None)
    run_parser.add_argument('--ticks', type=int, default=24)
    args = parser.parse_args(argv)
    if args.command == 'prepare':
        dest = prepare_tree(args.pinned_root, args.candidate, args.dest)
        print(json.dumps({'prepared': str(dest)}))
        return 0
    return run(args)


if __name__ == '__main__':
    sys.exit(main())
