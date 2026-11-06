#!/usr/bin/env python3
"""Prepare-only: the exact spawn plan for the geometry student client.

WHAT THIS DOES
--------------
Computes and prints the REAL argv, the REAL cwd, the REAL allowed environment
and the REAL source SHA256s that the candidate geometry client would use --
and NOTHING else.  It is a planner, not a launcher.

WHAT IT MUST NOT DO (and does not)
----------------------------------
* no research-module import: it imports only the Python standard library.  It
  never imports ``harness.*``, never imports the candidate client or worker;
* no head or worker start: it never calls ``subprocess``;
* no model load: it never opens the checkpoint's weights;
* no MuJoCo / simulator: it never imports ``sim.*`` or ``mujoco``;
* no network: it never opens a socket and never resolves a hostname.

It is therefore safe to run on a machine where the checkpoint cannot be loaded.
It DOES read source bytes and hash them -- that is its whole job -- and it
verifies the pins it is told about.

THE PLAN IT PRINTS
------------------
``argv``        the exact argument vector the client would spawn
``cwd``         the exact working directory the child would run in
``env``         the allowed environment (name -> value) the child would get
``sources``     every source file the plan depends on, with its sha256
``pins``        the pins the plan was checked against, and the verdict
``admitted``    whether the plan passes the pin gate

ONE LAUNCH PLAN, TWO CONSUMERS (fix-v1)
---------------------------------------
``build_launch_plan`` is the SINGLE stdlib-only builder of the launch plan.
Both the prepare-only CLI below AND the candidate client
(``solo_geometry_client.py``) call it, so the plan that is printed is the
plan that is actually executed -- there is no second, drifting copy of the
argv/cwd/env.  The client then compares the argv/cwd/env it really handed
to ``Popen`` against this very plan and records the comparison.

``argv_base`` is the part the PINNED ``SoloStudentClient`` builds itself
(``python <worker> --model ... --config ... --device ...``); ``argv_extra``
is the part this candidate adds (``--threads``, ``--predictor``).  The client
REFUSES to spawn if the pinned client's own argv differs from ``argv_base``.

The environment is EXPLICIT: ``env`` is the complete mapping the child is
started with.  It is the pinned keys plus a short, named pass-through list
(``ENV_PASSTHROUGH``) -- the child does NOT inherit the parent environment
wholesale.

REJECTION RULES
---------------
* a missing or tampered source file (sha256 != pin) -> rejected;
* an unknown checkpoint kind (adapter schema that is not
  ``ugrp.grasp_act.adapter.pairact_geometry.v1``) -> rejected;
* a config whose ``mode`` is not ``pairact_r1_v1`` -> rejected;
* a config whose stage list is not the pinned 8-stage order -> rejected;
* a ``--pins`` override that tries to REPLACE a base pin -> rejected, and the
  base pin is kept (the override is ADD-only);
* a malformed ``--pins`` file (bad JSON, non-object, bad record) -> rejected
  with a clear message.

The ``--pins`` override is ADD-only (fix-v2): the base pins are mandatory and
immutable, so a caller can add a pin but can never re-point an existing one
at a substituted file with a self-consistent digest.  The plan records what
the override did under ``pin_gate.override`` (``added`` / ``collisions`` /
``errors``).

The checkpoint check reads ``adapter.json`` (a TEXT manifest), never
``model.safetensors``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

#: The pinned 8-stage order the checkpoint and the executor agree on.
PINNED_STAGES = ['approach', 'alignment', 'ready', 'execute', 'carry', 'place', 'recover', 'complete']

#: The one adapter schema this candidate is written for.
PINNED_ADAPTER_SCHEMA = 'ugrp.grasp_act.adapter.pairact_geometry.v1'

#: The config mode the pinned loader accepts.
PINNED_CONFIG_MODE = 'pairact_r1_v1'

#: Pinned sources.  ``path`` is where the file is read from; ``sha256`` is the
#: expected digest.  A missing or different digest rejects the plan.
PINNED_SOURCES = {
    'pinned_solo_worker': {
        'path': '/home/ubuntu/UGRP/experiments/2026-11-04-solo-carry-student-wire/work/scripts/pairact_solo_student_worker.py',
        'sha256': 'c0938793b01cdac798aaf662d686074b4e66db6c6b0d5622f9f81ea87d754178',
        'role': 'the pinned four-op worker module the child loads by path',
    },
    'staged_solo_client': {
        'path': '/home/ubuntu/UGRP/experiments/2026-11-04-solo-act-worker-boot-v1/candidate/staging/harness/solo_student_eval.py',
        'sha256': '79a480854d4d52b6f09b796cac9d79360b3721e095e509f900589886c715edb7',
        'role': 'the pinned SoloStudentClient / SoloStudentEpisode / RearmingSync',
    },
    'staged_solo_carry_contract': {
        'path': '/home/ubuntu/UGRP/experiments/2026-11-04-solo-act-worker-boot-v1/candidate/staging/harness/solo_carry_contract.py',
        'sha256': 'd6899efc36b3440210ae778b1f26e2f37a15f6d46f830c6f9795776083b5423c',
        'role': 'the staged solo carry contract (observation whitelist)',
    },
    'merged_namespace': {
        'path': '/home/ubuntu/UGRP/experiments/2026-11-04-solo-act-worker-boot-v1/candidate/bootstrap/merged_ns.py',
        'sha256': '0bbc7d70f00b09bcc595e5133c9e7a01bc3fcedc44ae3fd52e0f386122db80d9',
        'role': 'the merged harness namespace builder',
    },
    'loader_bind': {
        'path': '/home/ubuntu/UGRP/experiments/2026-11-04-joint-carry-geom-loader-bind-v1/candidate/loader_bind.py',
        'sha256': '666630abe4e1e53e8f603adae937b9bbd1c093c3633e2a1a595aac803ab7def0',
        'role': 'adapter_meta / dispatch / executor_view (the loader gates)',
    },
    'geometry_loader': {
        'path': '/home/ubuntu/ugrp-retrain-geom-20261029/implementation/geometry_policy.py',
        'sha256': '3681da67642f681615b42673ae004690d2341d62b99c3c6caeae647c8851788f',
        'role': 'GeometryActor.load for the pairact_geometry schema',
    },
    'v6_contract': {
        'path': '/home/ubuntu/ugrp-retrain-geom-20261029/source/original-full/harness/grasp_act_contract.py',
        'sha256': '6bc58d6f9707abd5d854c6dbbb63357ed14dab6c37bcf055ddd8d1d66d171056',
        'role': 'the v6 student contract the checkpoint pins',
    },
    'pairact_executor': {
        'path': '/home/ubuntu/ugrp-retrain-geom-20261029/source/original-full/harness/pairact_r1.py',
        'sha256': '8a9869248740bf5ad2da7194cdd9a582347ac09e88783cd6ea127ef3f208a210',
        'role': 'PairActBarrier / PairActChunkExecutor / load_config',
    },
    'p5_config': {
        'path': '/home/ubuntu/UGRP/experiments/2026-11-04-joint-carry-p5-worker-telemetry-seam-v1/config/pairact-r1.json',
        'sha256': '30ffca1812239eb585e99478069085032cf594f7df016d46f2a7fbe0c17debea',
        'role': 'the 8-stage pairact-r1 train config',
    },
}

#: The candidate's own files.  Their digest is reported, not pinned here (they
#: are the thing being reviewed), but the client re-checks the child's digest
#: at spawn time against an INDEPENDENT embedded pin.
CANDIDATE_SOURCES = {
    'candidate_geometry_worker': 'solo_geometry_worker.py',
    'candidate_geometry_client': 'solo_geometry_client.py',
}

#: The environment keys the child gets EXACTLY as they are pinned here.
PINNED_ENV_KEYS = (
    'PYTHONPATH', 'PYTHONDONTWRITEBYTECODE', 'CUDA_VISIBLE_DEVICES',
    'UGRP_SOLO_OVERLAY', 'UGRP_SOLO_ARCHIVED', 'UGRP_SOLO_TREE',
)

#: The ONLY parent variables passed through, in addition to the pinned ones.
#: The child therefore starts with an EXPLICIT environment; it does not
#: inherit the parent environment wholesale.
ENV_PASSTHROUGH = ('PATH', 'HOME', 'LANG', 'LC_ALL', 'TMPDIR', 'LD_LIBRARY_PATH')

#: The candidate predictor branches the child understands.
PREDICTORS = ('geometry', 'synthetic')


def pinned_env(candidate_root: Path) -> dict:
    """The six pinned environment keys, computed from the candidate root."""
    return {
        'PYTHONPATH': ':'.join([
            str(candidate_root),
            '/home/ubuntu/UGRP/experiments/2026-11-04-solo-act-worker-boot-v1/candidate/bootstrap',
            '/home/ubuntu/ugrp-retrain-geom-20261029/implementation',
            '/home/ubuntu/UGRP/experiments/2026-11-04-joint-carry-geom-loader-bind-v1/candidate',
        ]),
        'PYTHONDONTWRITEBYTECODE': '1',
        'CUDA_VISIBLE_DEVICES': '',
        'UGRP_SOLO_OVERLAY': '/home/ubuntu/UGRP/experiments/2026-11-04-solo-act-worker-boot-v1/candidate/staging',
        'UGRP_SOLO_ARCHIVED': '/home/ubuntu/ugrp-retrain-geom-20261029/source/original-full',
        'UGRP_SOLO_TREE': '/home/ubuntu/UGRP/experiments/2026-11-04-solo-carry-student-wire/work',
    }


def build_launch_plan(*, python, source, model, config, device='cpu', threads=1,
                      predictor='synthetic', worker=None) -> dict:
    """THE launch plan: argv, cwd and the explicit child environment.

    Standard library only.  It starts nothing, imports no research module and
    performs no gate check: it is the single description of HOW the child is
    launched.  ``prepare_only.py`` and ``solo_geometry_client.py`` both call
    it, so the printed plan and the executed plan cannot drift apart.

    ``argv_base``   what the PINNED client builds on its own
    ``argv_extra``  what this candidate adds (``--threads``, ``--predictor``)
    ``argv``        the complete argument vector handed to ``Popen``
    ``cwd``         the child's working directory
    ``env``         the COMPLETE environment mapping the child is started with
    """
    candidate_root = Path(__file__).resolve().parent
    worker_path = Path(worker) if worker is not None else candidate_root / 'solo_geometry_worker.py'
    if str(predictor) not in PREDICTORS:
        raise ValueError(f'unknown predictor {predictor!r} (expected one of {PREDICTORS})')
    argv_base = [str(python), str(worker_path), '--model', str(model),
                 '--config', str(config), '--device', str(device)]
    argv_extra = ['--threads', str(int(threads)), '--predictor', str(predictor)]
    env = {key: os.environ[key] for key in ENV_PASSTHROUGH if key in os.environ}
    env.update(pinned_env(candidate_root))
    return {
        'schema': 'ugrp.solo_geometry_client.launch_plan.v1',
        'argv_base': argv_base,
        'argv_extra': argv_extra,
        'argv': argv_base + argv_extra,
        'cwd': str(source),
        'env': env,
        'env_pinned_keys': list(PINNED_ENV_KEYS),
        'env_passthrough_keys': [key for key in ENV_PASSTHROUGH if key in os.environ],
        'env_inherits_parent_wholesale': False,
        'predictor': str(predictor),
        'threads': int(threads),
        'device': str(device),
        'worker': str(worker_path),
        'python': str(python),
        'source': str(source),
        'model': str(model),
        'config': str(config),
    }


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_pins(pins_path: str | None) -> tuple[dict, dict]:
    """The pin set to check against, and what the override did.

    WITHOUT ``--pins`` this is the base table above.

    WITH ``--pins`` the file is an **ADD-ONLY** extension: it may only ADD
    names that the base table does not define.  An attempt to REPLACE a base
    pin (including an identical same-name resubmission) is REFUSED with an
    explicit rejection and the base pin is left untouched -- the base pins
    are mandatory and their path, hash and role are immutable.

    Rationale (fix-v2, S1): with a replace-capable override, a caller could
    point the gate at a substituted ``staged_solo_client`` with a
    self-consistent digest and the gate would still report ``admitted=true``.
    That made "the pinned client is reused unchanged" an assumption instead
    of an enforced property.

    Malformed JSON, a non-object file, a non-object record or a record
    missing ``path`` / ``sha256`` / ``role`` are refused with a clear
    message; the base pins keep being checked either way.

    Returns ``(pins, info)`` where ``info`` records the override:
    ``added`` / ``collisions`` / ``errors`` / ``base_pins_unchanged``.
    """
    pins = {name: dict(record) for name, record in PINNED_SOURCES.items()}
    info = {'path': pins_path, 'mode': 'add_only', 'added': [], 'collisions': [],
            'errors': [], 'base_pins_unchanged': True, 'base_pin_count': len(pins)}
    if not pins_path:
        return pins, info
    try:
        raw = json.loads(Path(pins_path).read_text())
    except Exception as error:
        info['errors'].append(f'pins override is not readable JSON: {error!r}')
        return pins, info
    if not isinstance(raw, dict):
        info['errors'].append('pins override must be a JSON object of '
                              '{name: {path, sha256, role}}')
        return pins, info
    for name, record in raw.items():
        if not isinstance(name, str) or not name:
            info['errors'].append(f'pins override name {name!r} is not a non-empty string')
            continue
        if not isinstance(record, dict):
            info['errors'].append(f'pins override entry {name!r} must be an object, '
                                  f'got {type(record).__name__}')
            continue
        missing = [key for key in ('path', 'sha256', 'role') if key not in record]
        if missing:
            info['errors'].append(f'pins override entry {name!r} is missing {missing}')
            continue
        if not all(isinstance(record[key], str) and record[key]
                   for key in ('path', 'sha256', 'role')):
            info['errors'].append(f'pins override entry {name!r} needs non-empty string '
                                  'path, sha256 and role')
            continue
        if name in PINNED_SOURCES:
            info['collisions'].append({
                'name': name,
                'refused': True,
                'reason': 'base pins are mandatory and immutable; an override may only ADD',
                'base': dict(PINNED_SOURCES[name]),
                'attempted': {key: record[key] for key in ('path', 'sha256', 'role')},
            })
            continue
        pins[name] = {'path': record['path'], 'sha256': record['sha256'], 'role': record['role']}
        info['added'].append(name)
    return pins, info


def check_sources(pins: dict) -> tuple[dict, list]:
    sources, rejections = {}, []
    for name, record in pins.items():
        path = Path(record['path'])
        row = {'path': record['path'], 'expected_sha256': record['sha256'], 'role': record['role']}
        if not path.is_file():
            row['actual_sha256'] = None
            row['ok'] = False
            rejections.append(f'{name}: file is missing ({record["path"]})')
        else:
            actual = sha256_file(path)
            row['actual_sha256'] = actual
            row['ok'] = actual == record['sha256']
            if not row['ok']:
                rejections.append(f'{name}: sha256 mismatch {actual} != {record["sha256"]}')
        sources[name] = row
    return sources, rejections


def check_checkpoint(checkpoint: Path) -> tuple[dict, list]:
    """Read the adapter TEXT manifest only.  Never the weights."""
    rejections = []
    row = {'path': str(checkpoint), 'adapter_schema': None, 'model_sha256_read': False}
    adapter = checkpoint / 'adapter.json'
    if not adapter.is_file():
        rejections.append(f'checkpoint: adapter.json is missing ({adapter})')
        return row, rejections
    row['adapter_sha256'] = sha256_file(adapter)
    try:
        meta = json.loads(adapter.read_text())
    except Exception as error:
        rejections.append(f'checkpoint: adapter.json is unreadable ({error!r})')
        return row, rejections
    row['adapter_schema'] = meta.get('schema')
    if meta.get('schema') != PINNED_ADAPTER_SCHEMA:
        rejections.append(f'checkpoint: unknown adapter kind {meta.get("schema")!r} '
                          f'(expected {PINNED_ADAPTER_SCHEMA!r})')
    if meta.get('inference_geometry_input') != 'predicted_from_own_rgb_only':
        rejections.append('checkpoint: inference geometry input contract is not own-RGB-only')
    return row, rejections


def check_config(config: Path) -> tuple[dict, list]:
    rejections = []
    row = {'path': str(config)}
    if not config.is_file():
        rejections.append(f'config: missing ({config})')
        return row, rejections
    row['sha256'] = sha256_file(config)
    try:
        data = json.loads(config.read_text())
    except Exception as error:
        rejections.append(f'config: unreadable ({error!r})')
        return row, rejections
    row['mode'] = data.get('mode')
    row['stages'] = list(data.get('stages', []))
    row['issued_clock_deadband'] = data.get('issued_clock_deadband')
    if data.get('mode') != PINNED_CONFIG_MODE:
        rejections.append(f'config: wrong mode {data.get("mode")!r} (expected {PINNED_CONFIG_MODE!r})')
    if row['stages'] != PINNED_STAGES:
        rejections.append(f'config: stage order is not the pinned 8-stage order: {row["stages"]!r}')
    return row, rejections


def build_plan(args) -> dict:
    """The plan: the ONE launch plan (shared with the client) plus the gates."""
    launch = build_launch_plan(python=args.python, source=args.source, model=args.model,
                                config=args.config, device=args.device, threads=args.threads,
                                predictor=args.predictor)

    candidate_root = Path(__file__).resolve().parent
    model = Path(args.model)
    config = Path(args.config)

    pins, info = load_pins(args.pins)

    sources, rejections = check_sources(pins)
    override_info = dict(info)
    for collision in info['collisions']:
        rejections.append(f'pins override: base pin {collision["name"]!r} may not be replaced '
                          f'(path/sha256/role are immutable); the base pin was kept')
    rejections += list(info['errors'])
    ckpt_row, ckpt_rejections = check_checkpoint(model)
    cfg_row, cfg_rejections = check_config(config)
    rejections += ckpt_rejections + cfg_rejections

    candidate_rows = {}
    for name, filename in CANDIDATE_SOURCES.items():
        path = candidate_root / filename
        candidate_rows[name] = {'path': str(path),
                                'sha256': sha256_file(path) if path.is_file() else None,
                                'exists': path.is_file()}

    return {
        'schema': 'ugrp.solo_geometry_client.prepare_only.v1',
        'mode': 'prepare_only',
        'guarantees': {
            'research_module_imported': False,
            'head_or_worker_started': False,
            'model_loaded': False,
            'mujoco_or_simulator_imported': False,
            'network_used': False,
            'subprocess_used': False,
        },
        'launch': launch,
        'argv': launch['argv'],
        'argv_base': launch['argv_base'],
        'argv_extra': launch['argv_extra'],
        'cwd': launch['cwd'],
        'env': launch['env'],
        'env_inherits_parent_wholesale': launch['env_inherits_parent_wholesale'],
        'sources': sources,
        'candidate_sources': candidate_rows,
        'checkpoint': ckpt_row,
        'config': cfg_row,
        'pin_gate': {'checked': len(sources), 'rejections': rejections,
                     'admitted': not rejections,
                     'override': override_info},
        'not_claimed': [
            'this plan does not prove the child can start',
            'this plan does not prove the checkpoint loads',
            'this plan does not prove the model forwards',
            'this plan does not prove any robot, physics, SIM or GPU behaviour',
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', default='/usr/bin/python3')
    parser.add_argument('--source', default='/home/ubuntu/UGRP/experiments/2026-11-04-solo-carry-student-wire/work')
    parser.add_argument('--model', default='/home/ubuntu/ugrp-retrain-geom-20261029/checkpoints/step-020000/actor')
    parser.add_argument('--config', default='/home/ubuntu/UGRP/experiments/2026-11-04-joint-carry-p5-worker-telemetry-seam-v1/config/pairact-r1.json')
    parser.add_argument('--device', default='cpu')
    parser.add_argument('--threads', type=int, default=1)
    parser.add_argument('--predictor', choices=PREDICTORS, default='synthetic')
    parser.add_argument('--pins', default=None,
                        help='JSON file ADDING pins to the mandatory base set (ADD-only: '
                             'an existing pin name may not be replaced)')
    parser.add_argument('--out', default=None)
    args = parser.parse_args()

    plan = build_plan(args)
    text = json.dumps(plan, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text, encoding='utf-8')
    print(text)
    return 0 if plan['pin_gate']['admitted'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
