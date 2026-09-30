"""Two-commit registration receipts. Verification never follows blinded raw paths."""
from __future__ import annotations

import ast
import copy
import hashlib
import importlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent.parent
SOURCE = '4c6b439f3f7c9a147c901f8b260a1e214d4eb396'
CLASSIFIER_COMMIT = '1f0e4eb501a8f1b87077df943382fc1f0777dc69'
METADATA_COMMIT = 'e78ef70fb5004fed1dfef1866aaf99bbf0bdda41'
METADATA_DIR = 'experiments/2026-10-01-v6h1-confirm-blinded'
PREVIEW_SHA256 = 'a1f9d74d9417afe89a33eb90a4e00a0ebb8da7504aa4da734209869119ad1beb'
METADATA_HASHES = {
    'RUN_MANIFEST.json': '99723de36d20a55f348ea5b25ca203cf1db910dd9a620d3a8c4a17f27407f210',
    'plan.json': 'd627f9cda827d07bab5b86c04f9e45ffceb474e97a8dda566c4956372d5fb026',
    'placements_seed943_first12.json': '9c2cc220901084f4211952b57ccb4779570d61c926cc8bbbbf9c1f25be310b0a',
}
EXTRA = ('scripts/zone_pair_v6h_admission.py', 'scripts/zone_teacher.py',
         'sim/masterpi_dynamics_calibration.json', 'sim/masterpi_scene.xml',
         'maps/zones/zone_wide_door.json', 'harness/wrist_zone_skill_v9.py')
ANALYSIS_EXTRA = (
    'analysis/classify_placements.py', 'analysis/recorder_v4c6b.py',
    'analysis/CLASSIFY_NOTES.md', 'analysis/seal_registration.py',
    'analysis/analysis_gate.json', 'analysis/apply_sealed_analysis.py',
    'analysis/seal/disclosure.json', 'analysis/seal/execution_preview_4c6b439f.json',
    'analysis/seal/RUN_MANIFEST.json', 'analysis/seal/plan.json',
    'analysis/seal/placements_seed943_first12.json',
)


def git(*args):
    # A shared core.worktree setting must never redirect this audit.
    return subprocess.check_output(['git', '-C', str(ROOT), '-c', 'core.worktree=' + str(ROOT), *args])


def sha(data):
    return hashlib.sha256(data).hexdigest()


def blob_sha(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def pins(paths, commit=None):
    return {path: {'git_blob_sha': blob_sha(raw), 'sha256': sha(raw)}
            for path in sorted(paths)
            for raw in [git('show', commit + ':' + path) if commit else (ROOT/path).read_bytes()]}


def frozen_preview():
    raw = (HERE/'analysis/seal/execution_preview_4c6b439f.json').read_bytes()
    if sha(raw) != PREVIEW_SHA256:
        raise ValueError('frozen execution preview changed')
    return json.loads(raw)


def metadata():
    values = {}
    for name, expected in METADATA_HASHES.items():
        raw = git('show', METADATA_COMMIT + ':' + METADATA_DIR + '/' + name)
        if sha(raw) != expected or (HERE/'analysis/seal'/name).read_bytes() != raw:
            raise ValueError('committed blinded metadata mismatch: ' + name)
        values[name] = json.loads(raw)
    return values


def case_bytes(cases):
    # Preserve key order, numeric spelling and every field except the receipt ID.
    clean = [{k: v for k, v in c.items() if k != 'registration_run_id'} for c in cases]
    return json.dumps(clean, indent=2, allow_nan=False).encode()


def verify_cases(cases):
    plan_raw = git('show', METADATA_COMMIT + ':' + METADATA_DIR + '/plan.json')
    text = plan_raw.decode()
    start = text.index('"cases": ') + len('"cases": ')
    plan_cases, consumed = json.JSONDecoder().raw_decode(text[start:])
    expected = text[start:start + consumed].encode()
    actual = case_bytes(cases).replace(b'\n', b'\n  ')
    if actual != expected:
        raise ValueError('builder cases differ byte-for-byte from committed blinded plan')
    if len(cases) != 72 or sum(c['seed'] == 941 for c in cases) != 60:
        raise ValueError('require fixed 60+12 cases')
    return {'count': 72, 'primary': 60, 'sensitivity': 12,
            'serialization': 'plan.json literal cases array; original key order and numeric values; only registration_run_id removed',
            'plan_cases_sha256': sha(expected), 'builder_cases_sha256': sha(actual)}


def source_closure(paths, commit=None):
    if commit is None:
        from scripts.zone_pair_v6_contract import python_source_closure
        return set(python_source_closure(paths))
    # Resolve imports using only the seal tree. Later worktrees may legitimately
    # change the same paths without changing this historical analysis receipt.
    roots = sorted({path.split('/')[0] for path in paths})
    available = set(git('ls-tree', '-r', '--name-only', commit, '--', *roots).decode().splitlines())
    seen, pending = set(), list(paths)
    while pending:
        path = pending.pop()
        if path in seen:
            continue
        seen.add(path)
        if not path.endswith('.py'):
            continue
        for node in ast.walk(ast.parse(git('show', commit + ':' + path), filename=path)):
            modules = []
            if isinstance(node, ast.Import):
                modules = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                prefix = node.module or ''
                if node.level:
                    parent = path[:-3].split('/')
                    prefix = '.'.join(parent[:-node.level] + ([prefix] if prefix else []))
                modules = [prefix, *(prefix + '.' + a.name for a in node.names)]
            for module in modules:
                parts = module.split('.')
                for i in range(1, len(parts) + 1):
                    base = '/'.join(parts[:i])
                    for candidate in (base + '.py', base + '/__init__.py'):
                        if candidate in available and candidate not in seen:
                            pending.append(candidate)
    return seen


def analysis_paths(commit=None):
    # Conservative superset: all execution dependencies are pinned again at
    # analysis time, plus dynamic imports, definitions and the analysis gate.
    paths = set(frozen_preview()['v6_contract']['source_sha256'])
    paths.update(str((HERE/p).relative_to(ROOT)) for p in ANALYSIS_EXTRA)
    paths.add('experiments/2026-09-30-b-v6h-gain/analysis/gain_cohort_analysis.py')
    return source_closure(paths, commit)


def build_seal(preview):
    old = frozen_preview()
    execution = pins(old['v6_contract']['source_sha256'], SOURCE)
    if len(execution) != 274 or not set(EXTRA) <= execution.keys():
        raise ValueError('execution closure must contain all 274 files including six EXTRA')
    if {p: r['sha256'] for p, r in execution.items()} != old['v6_contract']['source_sha256']:
        raise ValueError('frozen execution closure hash mismatch')
    meta = metadata()
    case_receipt = verify_cases(preview['cases'])
    value = copy.deepcopy(preview)
    # Execution contracts are the recorded bytes, never a current-tree rebuild.
    for key in ('v6_contract', 'scene_contract', 'contact_profile_contract', 'fit', 'predecessor'):
        value[key] = old[key]
    value.update(state='sealed', sealed=True, status='DRAFT', runnable=False,
                 execution_source_sha=SOURCE, execution_status='recorded_blinded_before_seal',
                 execution_authorization=None, approval=None)
    value['pin_sets'] = {
        'execution': {'commit': SOURCE, 'verification': 'git show <commit>:<path>',
                      'extra_source_paths': list(EXTRA), 'files': execution},
        'analysis': {'commit_binding': 'commit containing these prereg_v6h.json bytes; pass --seal-commit',
                     'verification': 'git show <seal-commit>:<path>', 'files': pins(analysis_paths())},
    }
    value['analysis_gate'] = json.loads((HERE/'analysis/analysis_gate.json').read_text())
    value['case_equality'] = case_receipt
    value['notes'] = json.loads((HERE/'analysis/seal/disclosure.json').read_text())
    value['notes']['metadata'] = {'commit': METADATA_COMMIT, 'directory': METADATA_DIR,
                                 'sha256': METADATA_HASHES, 'cases_jsonl_sha256': meta['RUN_MANIFEST.json']['raw']['cases_jsonl_sha256'],
                                 'driver_sha256': meta['RUN_MANIFEST.json']['raw']['driver_py_sha256']}
    value['notes']['working_tree_differences'] = [
        {'path': p, 'execution_sha256': r['sha256'], 'seal_sha256': sha((ROOT/p).read_bytes())}
        for p, r in execution.items() if r['sha256'] != sha((ROOT/p).read_bytes())]
    value['changed_sealed_sources'] = old['changed_sealed_sources']
    value['qualification'] = ('Analysis sealed after blinded recording; not prospectively sealed execution admission; '
                              're-execution requires checkout ' + SOURCE + '; no new execution authorization')
    from scripts.zone_pair_authorization import digest, registration_payload
    value['registration_sha256'] = digest(registration_payload(value))
    return value


def recorded_seal_commit():
    path = str((HERE/'prereg_v6h.json').relative_to(ROOT))
    history = git('log', '--format=%H', 'HEAD', '--', path).decode().splitlines()
    return history[-1] if history else None


def verify_seal(value, seal_commit=None):
    seal_commit = seal_commit or recorded_seal_commit()
    from scripts.zone_pair_authorization import digest, registration_payload
    if value.get('state') != 'sealed' or value.get('sealed') is not True:
        raise ValueError('registration is not sealed')
    if value.get('registration_sha256') != digest(registration_payload(value)):
        raise ValueError('sealed registration hash mismatch')
    if value.get('runnable') is not False or value.get('execution_authorization') is not None:
        raise ValueError('analysis seal does not authorize current-tree execution')
    if seal_commit:
        committed = json.loads(git('show', seal_commit + ':' + str((HERE/'prereg_v6h.json').relative_to(ROOT))))
        if committed != value:
            raise ValueError('sealed state differs from seal commit')
    old = frozen_preview()
    execution = value['pin_sets']['execution']
    if (execution['commit'] != SOURCE or set(execution['files']) != set(old['v6_contract']['source_sha256'])
            or len(execution['files']) != 274 or execution['extra_source_paths'] != list(EXTRA)):
        raise ValueError('execution pin set incomplete or source changed')
    if execution['files'] != pins(execution['files'], SOURCE):
        raise ValueError('execution git blob/sha256 mismatch')
    if value['v6_contract'] != old['v6_contract'] or value['scene_contract'] != old['scene_contract']:
        raise ValueError('recorded execution contract changed')
    analysis = value['pin_sets']['analysis']['files']
    if set(analysis) != analysis_paths(seal_commit) or analysis != pins(analysis, seal_commit):
        raise ValueError('analysis pin set incomplete or git blob/sha256 mismatch')
    metadata()
    if value['case_equality'] != verify_cases(value['cases']):
        raise ValueError('case equality receipt changed')
    gate_path = str((HERE/'analysis/analysis_gate.json').relative_to(ROOT))
    gate = json.loads(git('show', seal_commit + ':' + gate_path) if seal_commit else (ROOT/gate_path).read_bytes())
    if value['analysis_gate'] != gate:
        raise ValueError('analysis gate changed')
    return {'status': 'verified_sealed', 'execution_commit': SOURCE, 'execution_files': 274,
            'analysis_files': len(analysis), 'analysis_commit': seal_commit or 'uncommitted working tree',
            'cases': 72, 'outcomes_read': False}
