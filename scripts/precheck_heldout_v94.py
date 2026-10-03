"""Headless v94 admission evidence, explicitly NOT a rendered collection.

Run only committed source under an owned SIM slot/physics lock. The production
Scene, reset, schedule, ports, timestep and abort guard are shared with collection.
No camera capture, candidate prediction, residual computation or fitting occurs.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import errno
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

import numpy as np

from harness import zone_final_pair_new_starts as v
from harness.kinematic_overlap import audit, digest, overlap, read_trace
from scripts import validate_consumer_criterion_b as frozen
from scripts.validate_consumer_criterion_b_v94 import CORPUS, ROOT, load_prior, sha, verify_frozen
from scripts.run_final_environment_checks import check_source, write


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n').encode()


def support(map_id):
    """Check every training-supported split/axis/sign/level/horizon cell.

    Steps: +/- .01/.02/.03, PRBS: +/- .02. PRBS signs label the *start command*
    of a complete B window, not a fictitious 3.2-second constant PRBS chip.
    """
    gate = frozen.criterion()
    result = []
    events = v.schedule(v.CHECK, map_id)
    for rid in v.ROBOTS:
        plan = v.design(v.CHECK, map_id, rid)
        u, segments, required = frozen.plan_arrays(plan, 7400, .05, include_required_ticks=True)
        observed, seen = np.zeros_like(u), set()
        for e in events:
            a = e['action']
            if e['robot_id'] != rid or a['kind'] != 'mecanum':
                continue
            k = round(e['t']/.05)
            if (k in seen or not 0 <= k < len(u) or abs(e['t']-k*.05) > 1e-9
                    or a['duration_s'] != .05):
                raise ValueError('invalid v94 schedule tick/lease')
            observed[k] = [a[name] for name in frozen.COMMAND_AXES]
            seen.add(k)
        if seen != required or not np.array_equal(observed, u):
            raise ValueError('actual scheduled commands differ from measurement design')
        data = {'u': u, 'segments': segments, 'dt': .05}
        for axis, name in enumerate(frozen.AXES):
            if not frozen.axis_supported(data, axis, gate):
                raise ValueError('missing B support: '+rid+'/'+name)
            for split, levels in [('steps', [.01, .02, .03]), ('prbs', [.02])]:
                for horizon in gate['horizons_s']:
                    starts, k = frozen.c.windows(segments[name][split], horizon, .05)
                    for level in levels:
                        for sign in (-1, 1):
                            count = int(np.count_nonzero(np.isclose(u[starts, axis], sign*level, atol=1e-12, rtol=0)))
                            row = {'robot_id': rid, 'axis': name, 'split': split,
                                   'sign': sign, 'level': level, 'horizon_s': horizon,
                                   'complete_windows': count}
                            if count == 0:
                                raise ValueError('unsupported B cell: '+str(row))
                            result.append(row)
    return {'pass': True, 'cells': result, 'cell_count': len(result),
            'level_scope': 'steps +/-.01,.02,.03; PRBS +/-.02 at window start; same training family',
            'statistical_independence': False}


def binding():
    import hashlib
    bundles = {mid: v.bundle(mid) for mid in v.MAPS}
    files = set().union(*(set(b['source_sha256']) for b in bundles.values()))
    files.update(('scripts/precheck_heldout_v94.py', 'scripts/validate_consumer_criterion_b_v94.py',
                  'harness/kinematic_overlap.py', str(CORPUS.relative_to(ROOT)),
                  'experiments/2026-10-03-critb-heldout-v94/frozen.json'))
    return {'schema': 'ugrp.heldout_v94_binding.v1',
            'bundle_sha256': {m: digest(b) for m, b in bundles.items()},
            'schedule_sha256': {m: hashlib.sha256(json_bytes(v.schedule(v.CHECK, m))).hexdigest() for m in v.MAPS},
            'source_sha256': {p: sha(ROOT/p) for p in sorted(files)},
            'frozen_sha256': verify_frozen(), 'corpus_sha256': sha(CORPUS)}


def verify_receipt(directory, bundles=None):
    directory = Path(directory).resolve()
    receipt = json.loads((directory/'precheck.json').read_text())
    manifest = json.loads((directory/'SHA256SUMS.json').read_text())
    if (receipt.get('schema') != 'ugrp.heldout_v94_precheck.v1' or receipt.get('status') != 'PRECHECK_PASS'
            or receipt.get('collection') is not False or receipt.get('rendering') is not False
            or receipt.get('criterion_B_pass') is not None):
        raise ValueError('not a successful headless v94 precheck receipt')
    for name, expected in manifest.items():
        path = (directory/name).resolve()
        if not path.is_relative_to(directory) or not path.is_file() or sha(path) != expected:
            raise ValueError('precheck artifact missing/changed: '+name)
    actual_files = {str(p.relative_to(directory)) for p in directory.rglob('*')
                    if p.is_file() and p.name != 'SHA256SUMS.json'}
    if set(manifest) != actual_files or not {'precheck.json', 'binding.json'} <= actual_files:
        raise ValueError('precheck manifest not exhaustive')
    expected_binding = binding()
    if json.loads((directory/'binding.json').read_text()) != expected_binding:
        raise ValueError('v94 precheck source/bundle/schedule/corpus changed; rerun required')
    if receipt['binding_sha256'] != sha(directory/'binding.json'):
        raise ValueError('precheck binding hash mismatch')
    if set(receipt['maps']) != set(v.MAPS) or receipt['denominator'] != 4:
        raise ValueError('precheck must contain two maps and both robots')
    for value in bundles or []:
        v.validate_bundle(value)
        bare = {k: val for k, val in value.items() if k not in ('source_sha', 'case')}
        if digest(bare) != expected_binding['bundle_sha256'][value['map_id']]:
            raise ValueError('collection bundle differs from precheck')
    return receipt


def commitment_hashes(directory):
    directory = Path(directory)
    b = json.loads((directory/'binding.json').read_text())
    return {'precheck.json': sha(directory/'precheck.json'),
            'SHA256SUMS.json': sha(directory/'SHA256SUMS.json'),
            'binding.json': sha(directory/'binding.json'),
            **{'bundle '+mid: value for mid, value in b['bundle_sha256'].items()},
            **{'schedule '+mid: value for mid, value in b['schedule_sha256'].items()},
            **{name: b['source_sha256'][name] for name in (
                'scripts/validate_consumer_criterion_b_v94.py', 'harness/kinematic_overlap.py',
                'scripts/precheck_heldout_v94.py', str(CORPUS.relative_to(ROOT)))}}


def verify_public_commitment(comment_id, directory, receipt):
    remote = json.loads(subprocess.check_output(['gh', 'api',
        f'repos/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/comments/{comment_id}'],
        text=True, timeout=30))
    if (remote.get('id') != comment_id or not remote.get('issue_url', '').endswith('/issues/219')
            or remote.get('created_at') != remote.get('updated_at')
            or 'V94_PRE_COLLECTION_COMMITMENT' not in remote.get('body', '')
            or not all(h in remote['body'] for h in commitment_hashes(directory).values())):
        raise ValueError('missing/edited/wrong #219 pre-collection commitment or hashes')
    committed = datetime.fromisoformat(remote['created_at'].replace('Z', '+00:00'))
    if not committed < datetime.now(timezone.utc):
        raise ValueError('commitment must precede collection')
    return {k: remote[k] for k in ('id', 'html_url', 'issue_url', 'created_at', 'updated_at', 'body')}


def run(output, expected_sha, *, host_snapshot):
    from scripts.run_final_pair_new_starts import run_case
    from sim.final_pair_new_starts import PhysicsBackend
    import mujoco
    check_source(expected_sha)
    prior = load_prior()
    frozen_hashes = verify_frozen()
    output.mkdir(parents=True, exist_ok=False)
    write(output/'binding.json', binding())
    report = {'schema': 'ugrp.heldout_v94_precheck.v1', 'status': 'PRECHECK_FAILED',
              'collection': False, 'rendering': False, 'criterion_B_pass': None,
              'source_sha': expected_sha, 'started_utc': datetime.now(timezone.utc).isoformat(),
              'binding_sha256': sha(output/'binding.json'), 'frozen_sha256': frozen_hashes,
              'environment': {'python': sys.version, 'platform': platform.platform(), 'mujoco': mujoco.__version__,
                              'numpy': np.__version__},
              'host_start': host_snapshot(), 'maps': {}, 'denominator': 4,
              'model_calls': 0, 'scope': 'HEADLESS_PRECHECK_ONLY_NOT_COLLECTION_NOT_B_SCORING'}
    try:
        new = []
        for mid in v.MAPS:
            supported = support(mid)
            b = {**v.bundle(mid), 'case': v.cases(v.CHECK, mid)[0], 'source_sha': expected_sha}
            result = run_case(b, output/mid, seed=v.SEED, host_snapshot=host_snapshot,
                backend_factory=lambda *a, **kw: PhysicsBackend(*a, **kw, render=False), precheck=True)
            if result['status'] != 'PRECHECK_ONLY' or not result['protocol_complete']:
                raise ValueError('headless replay failed: '+str(result.get('failure')))
            traces = [read_trace(output/mid/f'eval_only/{rid}/pose.jsonl') for rid in v.ROBOTS]
            motion = {}
            for rid, t in zip(v.ROBOTS, traces):
                if len(t.t) != 7401 or abs(t.t[-1]-t.t[0]-370.) > 1e-7:
                    raise ValueError('headless pose completeness failed')
                extents = np.ptp(t.states[:, :3], axis=0)
                if max(extents[:2]) <= 1e-4 or np.max(np.ptp(t.states[:, 3:], axis=0)) <= 1e-4:
                    raise ValueError('robot did not translate and rotate: '+rid)
                if result['minimum_wall_clearance_m'][rid] < .35-1e-10:
                    raise ValueError('unsafe full-path wall clearance: '+rid)
                # Check actual issued inputs, not just the authored design.
                u, _, ticks = frozen.plan_arrays(v.design(v.CHECK, mid, rid), 7400, .05,
                                                include_required_ticks=True)
                seen = set()
                for line in (output/mid/f'robots/{rid}/commands.jsonl').read_text().splitlines():
                    command = json.loads(line)
                    if command['kind'] != 'mecanum':
                        continue
                    k = round((command['t']-t.t[0])/.05)
                    if (k in seen or k not in ticks or command['duration_s'] != .05
                            or abs(command['t']-t.t[0]-k*.05) > 1e-7
                            or not np.array_equal(u[k], [command[a] for a in frozen.COMMAND_AXES])):
                        raise ValueError('issued headless commands differ from schedule')
                    seen.add(k)
                if seen != ticks:
                    raise ValueError('missing headless command ticks')
                motion[rid] = {'xyz_extent_m': extents.tolist(), 'command_ticks': len(seen),
                               'pose_samples': len(t.t), 'kinematic_sha256': t.sha256}
            novelty = audit(traces, prior)
            if novelty['status'] != 'DISJOINT':
                write(output/mid/'overlap.json', novelty)
                raise ValueError('PREVIOUSLY_SEEN_KINEMATICS')
            write(output/mid/'support.json', supported)
            write(output/mid/'overlap.json', novelty)
            new.extend(traces)
            report['maps'][mid] = {'support_cells': supported['cell_count'], 'support': True,
                'disjoint': True, 'motion': motion, 'minimum_wall_clearance_m': result['minimum_wall_clearance_m']}
        within = [{'a': a.source, 'b': b.source, 'overlap': overlap(a, b)}
                  for i, a in enumerate(new) for b in new[i+1:]]
        write(output/'within_cohort.json', within)
        if any(row['overlap'] for row in within):
            raise ValueError('new robot/map trajectories overlap each other')
        # Re-read inputs and source after physics; no changing corpus/source mid-run.
        if [t.sha256 for t in load_prior()] != [t.sha256 for t in prior]:
            raise ValueError('prior corpus changed during precheck')
        if json.loads((output/'binding.json').read_text()) != binding():
            raise ValueError('source changed during precheck')
        check_source(expected_sha)
        report['status'] = 'PRECHECK_PASS'
    except Exception as exc:
        report['failure'] = {'type': type(exc).__name__, 'message': str(exc),
                             'class': 'ENOSPC' if getattr(exc, 'errno', None) == errno.ENOSPC else 'HOST_ERROR'}
    finally:
        report.update(finished_utc=datetime.now(timezone.utc).isoformat(), host_end=host_snapshot())
        write(output/'precheck.json', report)
        write(output/'SHA256SUMS.json', {str(p.relative_to(output)): sha(p)
            for p in sorted(output.rglob('*')) if p.is_file() and p.name != 'SHA256SUMS.json'})
    return report


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--expected-source-sha', required=True)
    p.add_argument('--execute', action='store_true')
    p.add_argument('--lock-owner', choices=('codex', 'claude', 'kiro'), default='codex')
    p.add_argument('--sim-slot', required=True)
    args = p.parse_args(argv)
    if not args.execute:
        print(json.dumps({'status': 'PLAN_ONLY', 'maps': list(v.MAPS), 'rendering': False,
                          'support_cells': {mid: support(mid)['cell_count'] for mid in v.MAPS}}))
        return 0
    from scripts.agent_sim_slots import require_sim_slot, sim_snapshot
    from scripts.agent_lock import DEFAULT_ROOT
    branch = subprocess.check_output(['git', 'branch', '--show-current'], text=True).strip()
    require_sim_slot(DEFAULT_ROOT, slot=args.sim_slot, owner=args.lock_owner, branch=branch)
    primary = Path(subprocess.check_output(['git', 'rev-parse', '--path-format=absolute', '--git-common-dir'],
                                          text=True).strip()).parent
    if (not args.output.is_absolute() or not args.output.resolve().is_relative_to(primary/'outputs')
            or not args.output.name.startswith('heldout-v94-precheck-')):
        raise ValueError('precheck output must be a fresh primary outputs/heldout-v94-precheck-* directory')
    if shutil.disk_usage(primary).free < 10*1024**3:
        raise OSError(errno.ENOSPC, 'less than 10 GiB free')
    report = run(args.output, args.expected_source_sha, host_snapshot=lambda: sim_snapshot(DEFAULT_ROOT))
    print(json.dumps({'status': report['status'], 'failure': report.get('failure'), 'output': str(args.output)}))
    return 0 if report['status'] == 'PRECHECK_PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
