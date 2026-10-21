"""P2 seed mode: make_p2_cases.py --seed-start + make_seed_refs.py (pure functions, no physics)."""
import hashlib
import importlib.util
import json
import subprocess
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT/'experiments/2026-10-21-pairact-p2'
BASE = '90a99ee98'   # dsh/pairact-p2-carrypath-r-c3 before seed mode


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


p2 = _load('p2cases_seed', HERE/'make_p2_cases.py')
sr = _load('p2seedrefs', HERE/'make_seed_refs.py')


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _world(tmp, seed0=8343000, n=4, candidate='beamact5_r13', export_indices=None):
    """Synthetic wide_start cases + export dir + native refs dir, shaped like the gcp6 outputs."""
    start, export, refs = tmp/'wide-start', tmp/'export', tmp/'refs'
    for d in (start, export, refs):
        d.mkdir()
    cases = [{'plan': {'seed': seed0 + i, 'episode_id': f'beamact5-wide-{seed0 + i}'},
              'profile': {'scene_profile': 'walls_floor_contrast_v5_indigo110_s80'}, 'candidate': candidate}
             for i in range(n)]
    (start/'wide-cases.json').write_text(json.dumps(cases))
    (start/'wide-setup-funnel.json').write_text('{"funnel": []}')
    indices = list(range(n)) if export_indices is None else export_indices
    (export/'summary.json').write_text(json.dumps({'status': 'initialization_only', 'world_indices': indices,
        'cases_sha256': _sha((start/'wide-cases.json').read_bytes())}))
    (export/'canonical-scene.xml').write_text('<mujoco/>')
    proof, table = [], {}
    for k, ci in enumerate(indices):
        xml = export/f'world-{k:03d}'/'raw'/'scene.xml'
        xml.parent.mkdir(parents=True)
        xml.write_text(f'<mujoco seed="{seed0 + ci}"/>')
        native = _sha(f'native-{seed0 + ci}'.encode())
        folder = refs/'references'/native
        folder.mkdir(parents=True)
        (folder/'compiled-312.json').write_text('{}')
        (folder/'compiled-geometry312.npz').write_bytes(b'')
        table[native] = {'actuator': str(folder/'compiled-312.json'), 'geometry': str(folder/'compiled-geometry312.npz')}
        proof.append({'old_xml': str(xml), 'old_xml_sha256': _sha(xml.read_bytes()), 'native_xml_sha256': native})
    (refs/'per-world-references.json').write_text(json.dumps(table))
    (refs/'proof.json').write_text(json.dumps({'old_export': str(export), 'proof': proof}))
    return start/'wide-cases.json', export, refs


# --------------------------------------------------------------- make_seed_refs

def test_seed_series_and_bounds():
    assert sr.seed_series(8343000, 40) == list(range(8343000, 8343040))
    for bad in (0, 41):
        with pytest.raises(ValueError):
            sr.seed_series(8343000, bad)


def test_rng_collisions_rule():
    # rng = seed + i*10000 + attempt (wide_start.py); 9420000 is >= 400000 away -> impossible
    assert sr.rng_collisions(8343000, 9420000) == []
    hits = sr.rng_collisions(8343000, 8420000)
    assert hits and all(h['world_a'] - h['world_b'] == 8 and h['attempt_offset'] == 3000 for h in hits)


def test_plan_commands_follow_tonight_recipe():
    steps = dict(sr.plan_commands(8343000, 40))
    assert list(steps) == ['a_cases', 'b_export', 'c_refs', 'd_manifest', 'e_p2_cases']
    assert '--seed 8343000' in steps['a_cases'] and '--candidate beamact5_r13' in steps['a_cases']
    assert '--export-compiled-only' in steps['b_export'] and '--warp-native-contact-v1' not in steps['b_export']
    assert '--indices ' + ','.join(map(str, range(40))) in steps['b_export']
    assert '--rejection-table /home/ugrp/ugrp-sim/runs/beamact5/wide-start-8343000/wide-setup-funnel.json' in steps['b_export']
    assert '--old-export /home/ugrp/ugrp-sim/runs/beamact5/wide-export-old-8343000e' in steps['c_refs']
    assert '--indices 0,1,2,3,4 ' in dict(sr.plan_commands(8343000, 5))['b_export']


def test_manifest_binds_every_seed(tmp_path):
    cases, export, refs = _world(tmp_path)
    m = sr.build_manifest(8343000, 4, cases, export, refs)
    assert m['seeds'] == [8343000, 8343001, 8343002, 8343003]
    assert m['by_seed']['8343002']['native_xml_sha256'] == _sha(b'native-8343002')
    assert m['cases']['sha256'] == _sha(cases.read_bytes())
    assert m['rejection_table']['path'].endswith('wide-setup-funnel.json')


def test_manifest_rejects_unexported_seed_and_wrong_cases(tmp_path):
    cases, export, refs = _world(tmp_path, export_indices=[0, 1])
    with pytest.raises(ValueError, match='without exported world'):
        sr.build_manifest(8343000, 4, cases, export, refs)
    cases.write_text('[]')
    with pytest.raises(ValueError, match='cases_sha256'):
        sr.build_manifest(8343000, 2, cases, export, refs)


def test_check_init_replays_runtime_lookup(tmp_path):
    cases, export, refs = _world(tmp_path)
    m = sr.build_manifest(8343000, 4, cases, export, refs)
    init = tmp_path/'init'
    xml = init/'world-000'/'raw'/'scene.xml'
    xml.parent.mkdir(parents=True)
    xml.write_text('not exported')
    assert sr.check_init(m, init)['ok'] is False
    xml.write_text('native-8343000')          # sha(scene) == refs key
    assert sr.check_init(m, init) == {'ok': True, 'worlds': 1, 'missing': []}


# ------------------------------------------------------- make_p2_cases seed mode

def _manifest(tmp_path, **kw):
    cases, export, refs = _world(tmp_path, **kw)
    m = sr.build_manifest(8343000, len(json.loads((export/'summary.json').read_text())['world_indices']),
                          cases, export, refs)
    path = tmp_path/'seed-refs-manifest.json'
    path.write_text(json.dumps(m))
    return cases, m, path


def test_seed_mode_changes_only_candidate(tmp_path):
    cases, m, _ = _manifest(tmp_path)
    raw = cases.read_bytes()
    out = p2.derive_seeds(raw, m, p2.load_seed_refs(m), 8343001, 3, to='pairact_p2_r13_detour')
    src = json.loads(raw)
    assert [c['plan']['seed'] for c in out] == [8343001, 8343002, 8343003]
    assert [c['source_world_index'] for c in out] == [1, 2, 3]
    assert all(c['candidate'] == 'pairact_p2_r13_detour' for c in out)
    assert [{k: v for k, v in c.items() if k not in ('candidate', 'source_world_index')} for c in out] == \
           [{k: v for k, v in src[i].items() if k != 'candidate'} for i in (1, 2, 3)]


def test_seed_mode_missing_refs_is_explicit(tmp_path):
    cases, m, _ = _manifest(tmp_path)
    raw = cases.read_bytes()
    refs = p2.load_seed_refs(m)
    refs.pop(m['by_seed']['8343002']['native_xml_sha256'])
    with pytest.raises(SystemExit, match=r'MISSING_SEED_REFS: seeds \[8343002\]'):
        p2.derive_seeds(raw, m, refs, 8343000, 4)
    # compiled file deleted on disk -> entry dropped -> same explicit error
    Path(p2.load_seed_refs(m)[m['by_seed']['8343003']['native_xml_sha256']]['geometry']).unlink()
    with pytest.raises(SystemExit, match=r'MISSING_SEED_REFS: seeds \[8343003\]'):
        p2.derive_seeds(raw, m, p2.load_seed_refs(m), 8343003, 1)
    # gate40 manifest only covers its own seeds: asking beyond it fails before any case is written
    with pytest.raises(SystemExit, match='MISSING_SEED_CASES'):
        p2.derive_seeds(raw, m, p2.load_seed_refs(m), 8343002, 5)


def test_seed_mode_refuses_other_files(tmp_path):
    cases, m, _ = _manifest(tmp_path)
    with pytest.raises(ValueError, match='seed cases hash mismatch'):
        p2.derive_seeds(b'[]', m, p2.load_seed_refs(m), 8343000, 1)
    Path(m['refs']['path']).write_text('{}')
    with pytest.raises(ValueError, match='seed refs hash mismatch'):
        p2.load_seed_refs(m)


def test_seed_mode_requires_r13_candidate(tmp_path):
    cases, m, _ = _manifest(tmp_path, candidate='wide_start_D00_8343000')
    with pytest.raises(ValueError, match='expected candidate'):
        p2.derive_seeds(cases.read_bytes(), m, p2.load_seed_refs(m), 8343000, 1)


def test_seed_mode_cli_and_missing_refs_exit(tmp_path):
    cases, m, mpath = _manifest(tmp_path, export_indices=[0, 1])
    script = str(HERE/'make_p2_cases.py')
    ok = subprocess.run([sys.executable, script, '--seed-start', '8343000', '--n', '2', '--seed-cases', str(cases),
                         '--seed-refs-manifest', str(mpath), '--out', str(tmp_path/'o.json')],
                        capture_output=True, text=True)
    assert ok.returncode == 0, ok.stderr
    assert json.loads(ok.stdout)['seeds'] == [8343000, 8343001]
    bad = subprocess.run([sys.executable, script, '--seed-start', '8343000', '--n', '3', '--seed-cases', str(cases),
                          '--seed-refs-manifest', str(mpath), '--out', str(tmp_path/'o2.json')],
                         capture_output=True, text=True)
    assert bad.returncode == 1 and 'MISSING_SEED_REFS: seeds [8343002]' in bad.stderr
    assert not (tmp_path/'o2.json').exists()
    mixed = subprocess.run([sys.executable, script, '--seed-start', '8343000', '--out', str(tmp_path/'o3.json')],
                           capture_output=True, text=True)
    assert mixed.returncode == 2


# ------------------------------------------------------- default mode unchanged

def test_default_mode_bytes_identical_to_base(tmp_path, monkeypatch):
    """Default CLI output of the modified script == the pre-change script (git show BASE) on the same input."""
    try:
        old_src = subprocess.check_output(['git', 'show', f'{BASE}:experiments/2026-10-21-pairact-p2/make_p2_cases.py'],
                                          cwd=ROOT, text=True, stderr=subprocess.DEVNULL)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.fail(f'base commit {BASE} not in this clone: git fetch origin {BASE} (not skippable)')
    old = types.ModuleType('p2cases_base')
    old.__file__ = str(HERE/'make_p2_cases.py')    # same folder: FUNNEL path resolves identically
    exec(compile(old_src, f'{BASE}:make_p2_cases.py', 'exec'), old.__dict__)
    cases = [{'plan': {'seed': 8420000 + i}, 'profile': {'x': i}, 'candidate': 'beamact5_r13'} for i in range(40)]
    r13 = tmp_path/'wide-cases-r13.json'
    r13.write_text(json.dumps(cases))
    digest = _sha(r13.read_bytes())
    outs = []
    for mod, tag in ((old, 'old'), (p2, 'new')):
        for to in (None, 'pairact_p2_r13_detour'):
            monkeypatch.setattr(mod, 'R13_CASES_SHA256', digest)
            out = tmp_path/f'{tag}-{to}.json'
            argv = ['make_p2_cases.py', '--r13-cases', str(r13), '--out', str(out)] + (['--to', to] if to else [])
            monkeypatch.setattr(sys, 'argv', argv)
            mod.main()
            outs.append((tag, to, out.read_bytes()))
    old_bytes = {to: b for tag, to, b in outs if tag == 'old'}
    new_bytes = {to: b for tag, to, b in outs if tag == 'new'}
    assert old_bytes == new_bytes and len(old_bytes) == 2


def test_default_pins_unchanged():
    text = (HERE/'make_p2_cases.py').read_text()
    assert "R13_CASES_SHA256 = '3d4e065db0299c0efa4c91676f537ac9b0e130773e598dfc5767d97a34ffdc63'" in text
    assert "FUNNEL_SHA256 = '31027ffbdc5904a9a39a506e687a2138d9543906ec14ae6214292dc6f35f60c2'" in text
    assert p2.select_worlds(p2.load_funnel()) == (1, 11, 17)
