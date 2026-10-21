"""Fail-closed simulator version pins (pairact -c4), checked before any model/CUDA work.

Basis (repo records, not new choices):
- rollout (mjwarp_batch_v1): r13 gate/diag runs record ``"mujoco": "3.16.0"``
  (claude/beamact5-r2-t experiments/2026-10-17-beamact5/runs/gate39-r13-run/summary.json:17),
  the r3 gate log ``Warp 1.15.0 initialized`` (teacher/gate-40-r3/raw-fetch/gate39-r3-run.log.tail.txt:1),
  and the frozen MJWarp env experiments/2026-10-15-simalt3/evidence/warp-freeze.txt
  (mujoco==3.16.0, warp-lang==1.15.0, mujoco-warp archive 57b4692f).
- compiled reference export (--export-compiled-only): mujoco==3.12.0
  (run_warp_flow_teacher.py 'C312 reference export requires3.12'; evidence/c-freeze.txt).
gcp6 2026-10-21 (pairact-p3-detour-20261021T0320Z) found 3.12 where 3.16 was expected:
this stops such a run in seconds instead of after setup.
"""
import importlib.metadata
import json
import re

ROLLOUT = {'mujoco': '3.16.0', 'warp-lang': '1.15.0'}
EXPORT = {'mujoco': '3.12.0'}
MJWARP_COMMIT = '57b4692f4d3cdf4d27d916b4b8c4759ba36e9148'
MODES = ('rollout', 'export', 'none')


def installed(dist):
    try:
        return importlib.metadata.version(dist)
    except importlib.metadata.PackageNotFoundError:
        return None


def mjwarp_commit():
    """Commit of the installed mujoco-warp from PEP 610 direct_url.json, or None
    (e.g. installed from a local directory: unverifiable, recorded as such)."""
    try:
        raw = importlib.metadata.distribution('mujoco-warp').read_text('direct_url.json')
    except importlib.metadata.PackageNotFoundError:
        return None
    if not raw:
        return None
    info = json.loads(raw)
    commit = (info.get('vcs_info') or {}).get('commit_id')
    if commit:
        return commit
    m = re.search(r'/archive/([0-9a-f]{40})\.(?:tar\.gz|zip)', info.get('url', ''))
    return m.group(1) if m else None


def mode_for(physics_backend, export_compiled_only):
    if export_compiled_only:
        return 'export'
    return 'rollout' if physics_backend == 'mjwarp_batch_v1' else 'none'


def check(mode, *, versions=None, commit=None, module_mujoco=None):
    """Return the pin record; raise SystemExit('RUNTIME_PIN_MISMATCH: ...') on any
    difference. ``versions``/``commit``/``module_mujoco`` are injectable for tests."""
    if mode not in MODES:
        raise ValueError(f'unknown pin mode {mode!r}')
    want = ROLLOUT if mode == 'rollout' else EXPORT if mode == 'export' else {}
    have = versions if versions is not None else {d: installed(d) for d in ('mujoco', 'warp-lang')}
    if module_mujoco is None and mode != 'none':
        import mujoco                      # C library only; no CUDA context
        module_mujoco = mujoco.__version__
    bad = {d: {'want': v, 'have': have.get(d)} for d, v in want.items() if have.get(d) != v}
    if want and module_mujoco is not None and module_mujoco != want['mujoco']:
        bad['mujoco.__version__'] = {'want': want['mujoco'], 'have': module_mujoco}
    record = dict(mode=mode, want=want, have=have, mujoco_module=module_mujoco)
    if mode == 'rollout':
        got = commit if commit is not None else mjwarp_commit()
        record['mujoco_warp'] = dict(want=MJWARP_COMMIT, have=got,
                                     status='unverified_no_direct_url' if got is None else
                                     'match' if got == MJWARP_COMMIT else 'mismatch')
        if got is not None and got != MJWARP_COMMIT:
            bad['mujoco-warp'] = {'want': MJWARP_COMMIT, 'have': got}
    if bad:
        raise SystemExit('RUNTIME_PIN_MISMATCH: ' + json.dumps(bad, sort_keys=True)
                         + ' (see experiments/2026-10-21-pairact-p2/RUNBOOK_VENV.md)')
    return record
