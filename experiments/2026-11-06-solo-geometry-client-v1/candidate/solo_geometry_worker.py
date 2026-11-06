#!/usr/bin/env python3
"""Candidate child entry: the PINNED solo student worker + the geometry loader.

WHAT THIS IS
------------
The one place where the geometry checkpoint and the real solo wire are joined.
It is the CHILD side of the candidate ``SoloGeometryClient``: the parent speaks
the pinned ``harness.solo_student_eval.SoloStudentClient`` protocol to this
process over stdin/stdout, so this file must NOT be called directly to claim a
client connection (the previous experiment's ``child_entry.py`` was exactly
that shortcut, and it is not reused here for that purpose).

It REUSES, unchanged:
  * ``scripts/pairact_solo_student_worker.py`` (sha256 pinned) -- the real
    ``serve()``, the real 4-op allowlist, the real ``SoloStudentController``,
    the real ``harness.pairact_r1`` barrier/executor, the real issued-command
    clock;
  * ``2026-11-04-joint-carry-geom-loader-bind-v1/candidate/loader_bind.py``
    (sha256 pinned) -- ``adapter_meta`` / ``dispatch`` / ``executor_view``;
  * ``2026-11-04-solo-act-worker-boot-v1/candidate/bootstrap/merged_ns.py``
    (sha256 pinned) -- the merged ``harness`` namespace (OVERLAY -> ARCHIVED ->
    SOLO), so ``harness.grasp_act_contract`` resolves to the ARCHIVED v6 bytes
    the checkpoint pins.

WHAT IT CHANGES
---------------
Only the PREDICTOR SOURCE.  The default worker uses
``harness.pairact_r1.PairActActor.load``, whose schema gate accepts only
``ugrp.grasp_act.adapter.pairact_r1.v1`` and therefore refuses the 20k
geometry checkpoint (``ugrp.grasp_act.adapter.pairact_geometry.v1``).  The
geometry route uses ``loader_bind.dispatch`` -> ``GeometryActor.load`` for the
same schema, and projects the worker's three-key response onto the executor's
two-key view with the already-proven ``loader_bind.executor_view``.

The HELLO CONTRACT IS UNCHANGED AND CLOSED
-------------------------------------------
The pinned client checks the child's first line with ``==`` against exactly
``{'ready': True, 'mode': 'pairact_solo_student_eval_v1'}``.  The previous
experiment's child printed a LARGER hello dict, which would have been REJECTED
by the real client.  So this child prints exactly the closed hello and puts
every geometry diagnostic field in a SEPARATE side channel (stderr JSON line
prefixed ``GEOMETRY_DIAG ``), so the closed contract and the diagnostics cannot
be confused.  The client reads only stdout.

LOADER GATES ARE NOT RELAXED
-----------------------------
``loader_bind.checkpoint_manifest`` is NOT called by this worker -- the
submitted report claimed it was, which was wrong.  The ACTUAL gate on the
geometry route is ``GeometryActor.load`` itself: it verifies the checkpoint's
own three-file ``SHA256.json`` (contract / pairact / adapter digests), checks
the adapter contract fields, compares the draccus config with the
checkpoint's, and performs a strict ``load_state_dict``.  This worker
additionally reads ``SHA256.json`` itself and compares ``model.safetensors``
with the pinned digest BEFORE the load.  No gate is bypassed, and no gate is
claimed here that did not run.  (The synthetic branch loads no weights at
all, so no loader gate runs there either.)

FORWARD BUDGET
--------------
``--predictor geometry`` performs AT MOST ONE model forward for the whole
child (the counter is incremented BEFORE the forward, so a failed forward still
consumes the budget).  ``--predictor synthetic`` performs ZERO forwards and
loads NO weights: it is the CPU, non-physical, explicitly-labelled wire check.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

BOOTSTRAP = Path('/home/ubuntu/UGRP/experiments/2026-11-04-solo-act-worker-boot-v1/candidate/bootstrap')
IMPL = Path('/home/ubuntu/ugrp-retrain-geom-20261029/implementation')
LOADER_BIND = Path('/home/ubuntu/UGRP/experiments/2026-11-04-joint-carry-geom-loader-bind-v1/candidate')
SOLO_TREE = Path('/home/ubuntu/UGRP/experiments/2026-11-04-solo-carry-student-wire/work')
WORKER = SOLO_TREE / 'scripts/pairact_solo_student_worker.py'
CKPT = Path('/home/ubuntu/ugrp-retrain-geom-20261029/checkpoints/step-020000/actor')

PIN_WORKER_SHA256 = 'c0938793b01cdac798aaf662d686074b4e66db6c6b0d5622f9f81ea87d754178'
PIN_MERGED_NS_SHA256 = '0bbc7d70f00b09bcc595e5133c9e7a01bc3fcedc44ae3fd52e0f386122db80d9'
PIN_LOADER_BIND_SHA256 = '666630abe4e1e53e8f603adae937b9bbd1c093c3633e2a1a595aac803ab7def0'
PIN_GEOMETRY_SOURCE_SHA256 = '3681da67642f681615b42673ae004690d2341d62b99c3c6caeae647c8851788f'
EXPECT_MODEL_SHA256 = '1b998586bb02097ebf09782a227baeed853546548b0f388893e08ad95efd5155'

#: The exact closed hello the pinned client compares with ``==``.
HELLO = {'ready': True, 'mode': 'pairact_solo_student_eval_v1'}

#: Prefixes the diagnostic side channel on stderr; stdout carries the wire.
DIAG_PREFIX = 'GEOMETRY_DIAG '


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def emit_diag(payload: dict) -> None:
    """Diagnostic side channel: stderr only, never stdout (stdout is the wire)."""
    sys.stderr.write(DIAG_PREFIX + json.dumps(payload, ensure_ascii=False, allow_nan=False) + '\n')
    sys.stderr.flush()


def require_pin(path: Path, expected: str, what: str) -> str:
    if not Path(path).is_file():
        raise SystemExit(f'{what} is missing: {path}')
    actual = sha256_file(path)
    if actual != expected:
        raise SystemExit(f'{what} sha256 mismatch: {actual} != {expected}')
    return actual


def extract_hello(source: str) -> dict:
    """Read the worker's own hello literal out of its pinned source (not retyped)."""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and getattr(node.func, 'attr', None) == 'dumps' \
                and node.args and isinstance(node.args[0], ast.Dict):
            try:
                value = ast.literal_eval(node.args[0])
            except Exception:
                continue
            if isinstance(value, dict) and value.get('ready') is True and 'mode' in value:
                return value
    raise SystemExit('hello line not found in the pinned worker source')


def install_merged_namespace() -> dict:
    """Install the merged ``harness`` namespace in THIS process and prove it."""
    for path in (str(BOOTSTRAP), str(IMPL), str(LOADER_BIND)):
        if path not in sys.path:
            sys.path.insert(0, path)
    import merged_ns
    merged_ns.bind()
    import harness
    import harness.beamact3 as b3
    import harness.grasp_act_contract as c
    import harness.grasp_act_data as d
    import harness.grasp_act_policy as gp
    import harness.pairact_r1 as pr
    import harness.pairact_solo_student as pss
    import harness.solo_carry_contract as scc
    modules = {'harness.beamact3': b3, 'harness.grasp_act_contract': c,
               'harness.grasp_act_data': d, 'harness.grasp_act_policy': gp,
               'harness.pairact_r1': pr, 'harness.pairact_solo_student': pss,
               'harness.solo_carry_contract': scc}
    proof = {'harness_package': str(Path(harness.__file__).resolve().parent),
             'harness_path': list(harness.__path__),
             'merged_marker': bool(getattr(harness, '__ugrp_solo_merged_namespace__', False)),
             'init_error': getattr(harness, '__init_error__', None),
             'contract_schema': c.SCHEMA, 'context_dim': c.CONTEXT_DIM,
             'modules': {}}
    for name, module in modules.items():
        path = getattr(module, '__file__', None)
        proof['modules'][name] = {'file': path,
                                  'sha256': sha256_file(Path(path)) if path else None}
    if not proof['merged_marker']:
        raise SystemExit('merged harness namespace is NOT installed: ' + json.dumps(proof))
    if proof['init_error']:
        raise SystemExit('merged harness __init__ error: ' + str(proof['init_error']))
    return proof


def synthetic_predictor(stages, chunk: int, action_dim: int):
    """Deterministic NON-model predictor for the CPU, non-physical wire check.

    It returns the SAME three-key shape the real geometry response has, so the
    pinned ``executor_view`` projection and the pinned executor are exercised
    end to end WITHOUT loading weights and WITHOUT a model forward.  It is
    explicitly labelled synthetic; it proves the WIRE, not the model.

    The projection is NOT optional: the pinned executor accepts exactly
    ``{'chunk', 'stage_logits'}``, so the synthetic result is put through the
    same ``loader_bind.executor_view`` the geometry route uses.  The synthetic
    path and the geometry path therefore share ONE projection seam.
    """
    state = {'calls': 0}

    def raw(observation, jpegs):
        state['calls'] += 1
        rows, logits = [], []
        for offset in range(chunk):
            row = [0.0] * action_dim
            row[0] = 0.35
            row[4] = 0.10
            rows.append(row)
            index = offset % len(stages)
            logits.append([1.0 if j == index else 0.0 for j in range(len(stages))])
        return {'chunk': rows, 'stage_logits': logits, 'geometry': {'source': 'synthetic'}}

    raw.state = state
    return raw


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--model', default=str(CKPT))
    parser.add_argument('--device', default='cpu')
    parser.add_argument('--threads', type=int, default=1)
    parser.add_argument('--predictor', choices=('geometry', 'synthetic'), default='synthetic')
    parser.add_argument('--hello-extra', default='', help='ignored; reserved for diagnostics')
    args = parser.parse_args()

    worker_sha = require_pin(WORKER, PIN_WORKER_SHA256, 'pinned solo student worker')
    require_pin(BOOTSTRAP / 'merged_ns.py', PIN_MERGED_NS_SHA256, 'merged namespace module')
    require_pin(LOADER_BIND / 'loader_bind.py', PIN_LOADER_BIND_SHA256, 'loader_bind module')
    require_pin(IMPL / 'geometry_policy.py', PIN_GEOMETRY_SOURCE_SHA256, 'geometry loader source')

    proof = install_merged_namespace()
    worker_source = WORKER.read_text()
    hello = extract_hello(worker_source)
    if hello != HELLO:
        raise SystemExit('pinned worker hello is not the closed contract: ' + json.dumps(hello))

    spec = importlib.util.spec_from_file_location('pinned_pairact_solo_student_worker', WORKER)
    if spec is None or spec.loader is None:
        raise SystemExit('cannot load the pinned worker module')
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)

    import harness.grasp_act_contract as c
    from harness.pairact_r1 import STAGES, load_config

    config = load_config(args.config)

    diag = {'worker_file': str(WORKER), 'worker_sha256': worker_sha,
            'namespace': proof, 'predictor': args.predictor,
            'config_mode': config.get('mode'), 'config_stages': list(config.get('stages', [])),
            'issued_clock_deadband': config.get('issued_clock_deadband'),
            'contract_schema': c.SCHEMA, 'context_dim': c.CONTEXT_DIM,
            'stages': list(STAGES), 'chunk': c.CHUNK, 'action_dim': c.ACTION_DIM,
            'history': c.HISTORY, 'rgb_history': c.RGB_HISTORY,
            'model_forwards': 0}

    if args.predictor == 'synthetic':
        from loader_bind import executor_view
        raw = synthetic_predictor(STAGES, c.CHUNK, c.ACTION_DIM)

        def predict(observation, jpegs):
            # The SAME projection the geometry route uses: the pinned executor
            # accepts exactly {'chunk', 'stage_logits'}, so the geometry-shaped
            # three-key response is projected down by the pinned
            # loader_bind.executor_view.  One seam, both routes.
            return executor_view(raw(observation, jpegs), include_stage=True)

        predict.state = raw.state
        diag['note'] = 'SYNTHETIC predictor: no weights loaded, no model forward'
        diag['loader'] = None
        diag['loader_class'] = None
        diag['projection'] = 'loader_bind.executor_view(include_stage=True)'
        emit_diag(diag)
        # THE CLOSED HELLO, byte-for-byte the shape the pinned client expects.
        print(json.dumps(HELLO, allow_nan=False), flush=True)
        worker.serve(predict, sys.stdin, lambda s: print(s, flush=True), config=config)
        emit_diag({'done': True, 'predictor': 'synthetic', 'predict_calls': predict.state['calls'],
                   'model_forwards': 0})
        return 0

    # ---------------- real 20k geometry actor (CPU) ----------------
    import torch
    torch.set_num_threads(args.threads)
    if args.threads != 1:
        torch.set_num_interop_threads(1)

    from loader_bind import adapter_meta, dispatch, executor_view
    meta = adapter_meta(Path(args.model))
    loader = dispatch(meta)
    if loader != 'geometry_policy.GeometryActor.load':
        raise SystemExit('unexpected loader for the pinned schema: ' + repr(loader))

    manifest = json.loads((Path(args.model) / 'SHA256.json').read_text())
    actual_model_sha = sha256_file(Path(args.model) / 'model.safetensors')
    if actual_model_sha != EXPECT_MODEL_SHA256:
        raise SystemExit('checkpoint model sha256 mismatch: ' + actual_model_sha)

    from geometry_policy import GeometryActor
    actor = GeometryActor.load(args.model, device=args.device)
    devices = sorted({str(p.device) for p in actor.policy.parameters()})
    diag.update({'loader': loader, 'loader_class': f'{GeometryActor.__module__}.{GeometryActor.__name__}',
                 'geometry_source': str(Path(sys.modules['geometry_policy'].__file__)),
                 'geometry_source_sha256': sha256_file(Path(sys.modules['geometry_policy'].__file__)),
                 'checkpoint': str(args.model), 'manifest': manifest,
                 'model_sha256': actual_model_sha, 'adapter_sha256': manifest.get('adapter.json'),
                 'adapter_schema': meta.get('schema'),
                 'torch': torch.__version__, 'threads': args.threads,
                 'parameter_devices': devices, 'device': args.device})
    emit_diag(diag)
    print(json.dumps(HELLO, allow_nan=False), flush=True)

    counter = {'calls': 0, 'fwd': 0}

    def predict(observation, jpegs):
        counter['calls'] += 1
        if counter['fwd'] >= 1:
            raise RuntimeError('model forward budget exhausted (limit 1)')
        counter['fwd'] += 1
        result = actor.predict_staged(observation, jpegs)
        view = executor_view(result, include_stage=True)
        emit_diag({'event': 'geometry_prediction', 'forwards': counter['fwd'],
                   'result_keys': sorted(result), 'executor_view_keys': sorted(view),
                   'stage_logits': result['stage_logits'], 'geometry': result['geometry'],
                   'chunk': result['chunk'], 'observation_t': observation['t'],
                   'observation_sample_id': observation['sample_id'],
                   'issued_history_len': len(observation['issued']),
                   'rgb_sha256': [r['sha256'] for r in observation['rgb']]})
        return view

    worker.serve(predict, sys.stdin, lambda s: print(s, flush=True), config=config)
    emit_diag({'done': True, 'predictor': 'geometry', 'model_forwards': counter['fwd'],
               'predict_calls': counter['calls']})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
