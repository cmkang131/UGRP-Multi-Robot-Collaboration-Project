"""COLLECT_PREREG v7 fix (dsh/pairact-carry-r1-v7): Codex v6 re-review 2b (collect-v6-review-20261021).

2b: core bound only the sha256 of the --per-world-model-references-v1 JSON.  The wrapper opens the files that
JSON names -- actuator (compiled-312.json), geometry (compiled-geometry312.npz) and the geometry sidecar
(<geometry>.json, read by simalt_compiled_compat.apply_geometry) -- so their contents could change under one
core.  v7 binds a transitive digest (assets.per_world_reference_files_sha256) re-hashed by the manifest gate.
Every tamper below is refused at core and final with verify_assets; the untouched control is accepted.  CPU only.
"""
import copy
import hashlib
import json
import os
from pathlib import Path

import pytest

from harness import pairact_collect as pc
from test_pairact_collect import recording_dir
from test_pairact_collect_v5 import _asset_case, _register as _register_meshes, prereg_core

ROOT = Path(__file__).resolve().parents[1]
X1, X2, X3 = (hashlib.sha256(c.encode()).hexdigest() for c in ('scene-1', 'scene-2', 'scene-3'))


def _write_world(folder, tag):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'compiled-312.json').write_text(json.dumps(dict(mujoco='3.12.0', tag=tag)) + '\n')
    (folder / 'compiled-geometry312.npz').write_bytes(b'NPZ' + tag.encode())
    (folder / 'compiled-geometry312.npz.json').write_text(json.dumps(dict(npz=tag)) + '\n')
    return dict(actuator=str(folder / 'compiled-312.json'), geometry=str(folder / 'compiled-geometry312.npz'))


def _write_refs(a, refs):
    (a / 'refs.json').write_text(json.dumps(refs, indent=2) + '\n')


def _register(m, a):
    """What the VM fills: the JSON sha256 and the v7 transitive digest of the files it names."""
    m['assets']['per_world_model_references_sha256'] = pc.file_sha256(a / 'refs.json')
    m['assets']['per_world_reference_files_sha256'] = pc.per_world_reference_digest(str(a / 'refs.json'))


@pytest.fixture
def case(tmp_path):
    """Accepted control: two exact-XML worlds under the references JSON's directory, as the gcp6 runner writes."""
    a, m = _asset_case(tmp_path, '<mujoco><asset><mesh name="m" file="m.obj"/></asset></mujoco>\n', {'m.obj': 'mesh\n'})
    _register_meshes(m, a / 'm.obj')
    refs = {X1: _write_world(a / 'references' / X1, 'w1'), X2: _write_world(a / 'references' / X2, 'w2')}
    _write_refs(a, refs)
    _register(m, a)
    return tmp_path, a, m, refs


def _core(m):
    try:
        return pc.check_run_manifest(m, stage='core', prereg=prereg_core(), verify_assets=True), ''
    except ValueError as e:
        return None, str(e)


def _final(tmp_path, m, core):
    """FROZEN manifest whose recording files are bound to ``core`` (the core accepted before any tamper)."""
    d = tmp_path / f'final-{len(list(tmp_path.glob("final-*")))}'
    d.mkdir()
    rec, hashes = recording_dir(d, core=core)
    mf = copy.deepcopy(m)
    mf['status'] = 'FROZEN'
    mf['recording_check'].update(hashes)
    try:
        pc.check_run_manifest(mf, stage='final', prereg=dict(prereg_core(), status='FROZEN'), recording_dir=rec,
                              verify_assets=True)
        return ''
    except ValueError as e:
        return str(e)


def _refused(tmp_path, m, core, match):
    got_core = _core(m)
    assert got_core[0] is None and match in got_core[1], got_core
    got_final = _final(tmp_path, m, core)
    assert match in got_final, got_final


def test_control_is_accepted_at_core_and_final(case):
    tmp_path, a, m, refs = case
    core, err = _core(m)
    assert core and not err
    assert _final(tmp_path, m, core) == ''
    rel = [r for r, _ in pc.per_world_reference_files(str(a / 'refs.json'))]
    assert rel == sorted(f'references/{x}/{n}' for x in (X1, X2)
                         for n in ('compiled-312.json', 'compiled-geometry312.npz', 'compiled-geometry312.npz.json'))


def test_files_are_exactly_what_the_wrapper_opens(case):
    """Single reading: the files equal the wrapper's Path(ref['actuator']), Path(ref['geometry']) and
    apply_geometry's str(geometry) + '.json' -- and those read sites are still the ones in the repo."""
    _, a, _, _ = case
    refs = json.loads((a / 'refs.json').read_text())
    opened = {p for r in refs.values() for p in (r['actuator'], r['geometry'], r['geometry'] + '.json')}
    assert {p for _, p in pc.per_world_reference_files(str(a / 'refs.json'))} == opened
    assert "Path(ref['actuator']),Path(ref['geometry'])" in (ROOT / 'scripts/warp_act_backend.py').read_text()
    assert "Path(str(path)+'.json')" in (ROOT / 'scripts/simalt_compiled_compat.py').read_text()


@pytest.mark.parametrize('target', ['compiled-312.json', 'compiled-geometry312.npz'])
def test_one_byte_change_in_a_referenced_file_is_refused(case, target):
    tmp_path, a, m, _ = case
    core, _ = _core(m)
    path = a / 'references' / X2 / target
    data = bytearray(path.read_bytes())
    data[-1] ^= 1
    path.write_bytes(bytes(data))
    _refused(tmp_path, m, core, 'assets.per_world_reference_files_sha256 differs')


def test_replaced_file_same_name_other_content_is_refused(case):
    tmp_path, a, m, _ = case
    core, _ = _core(m)
    path = a / 'references' / X1 / 'compiled-geometry312.npz'
    path.unlink()
    path.write_bytes(b'NPZ-other-geometry')
    _refused(tmp_path, m, core, 'assets.per_world_reference_files_sha256 differs')


def test_sidecar_content_change_is_refused(case):
    """The geometry .json sidecar is a model input (apply_geometry reads it); JSON / npz unchanged."""
    tmp_path, a, m, _ = case
    core, _ = _core(m)
    (a / 'references' / X1 / 'compiled-geometry312.npz.json').write_text('{"npz": "edited"}\n')
    _refused(tmp_path, m, core, 'assets.per_world_reference_files_sha256 differs')


def test_missing_sidecar_is_refused(case):
    tmp_path, a, m, _ = case
    core, _ = _core(m)
    (a / 'references' / X2 / 'compiled-geometry312.npz.json').unlink()
    _refused(tmp_path, m, core, 'per-world reference file missing')


@pytest.mark.parametrize('edit', ['add', 'remove'])
def test_added_or_removed_reference_is_refused_even_with_the_json_rehashed(case, edit):
    """The JSON hash alone is re-registered (what v6 bound): the digest still refuses."""
    tmp_path, a, m, refs = case
    core, _ = _core(m)
    refs = dict(refs)
    if edit == 'add':
        refs[X3] = _write_world(a / 'references' / X3, 'w3')
    else:
        refs.pop(X2)
    _write_refs(a, refs)
    m['assets']['per_world_model_references_sha256'] = pc.file_sha256(a / 'refs.json')
    _refused(tmp_path, m, core, 'assets.per_world_reference_files_sha256 differs')


def test_reregistering_the_digest_is_a_different_core(case):
    """Re-filling both hashes after a tamper passes core only as another core_sha256: final, bound to the
    recording of the original core, refuses it."""
    tmp_path, a, m, _ = case
    core, _ = _core(m)
    (a / 'references' / X1 / 'compiled-312.json').write_text('{"mujoco": "3.12.0", "tag": "evil"}\n')
    _register(m, a)
    core2, err = _core(m)
    assert core2 and core2 != core and not err
    assert 'recording evidence of another core' in _final(tmp_path, m, core)


def _same_content_elsewhere(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(Path(src).read_bytes())
    return dst


def test_symlink_swap_with_identical_content_is_refused(case):
    """Even a symlink to a byte-identical copy (digest unchanged) is refused: its target can change later."""
    tmp_path, a, m, _ = case
    core, _ = _core(m)
    path = a / 'references' / X1 / 'compiled-312.json'
    copy_ = _same_content_elsewhere(path, tmp_path / 'outside' / 'compiled-312.json')
    path.unlink()
    path.symlink_to(copy_)
    _refused(tmp_path, m, core, 'goes through a symlink')


def test_symlinked_directory_is_refused(case):
    tmp_path, a, m, _ = case
    core, _ = _core(m)
    folder = a / 'references' / X2
    moved = tmp_path / 'outside' / X2
    moved.parent.mkdir(parents=True, exist_ok=True)
    folder.rename(moved)
    folder.symlink_to(moved, target_is_directory=True)
    _refused(tmp_path, m, core, 'goes through a symlink')


def test_symlinked_references_json_is_refused(case):
    tmp_path, a, m, _ = case
    core, _ = _core(m)
    real = _same_content_elsewhere(a / 'refs.json', a / 'real-refs.json')
    (a / 'refs.json').unlink()
    (a / 'refs.json').symlink_to(real)
    _refused(tmp_path, m, core, 'references JSON is a symlink')


@pytest.mark.parametrize('kind', ['outside', 'dotdot', 'relative'])
def test_path_outside_the_root_is_refused(case, kind):
    tmp_path, a, m, refs = case
    core, _ = _core(m)
    outside = _write_world(tmp_path / 'outside' / X1, 'w1')            # identical bytes, outside the root
    refs = copy.deepcopy(refs)
    if kind == 'outside':
        refs[X1] = outside
    elif kind == 'dotdot':
        refs[X1]['actuator'] = str(a / '..' / 'outside' / X1 / 'compiled-312.json')
    else:
        refs[X1]['actuator'] = os.path.relpath(refs[X1]['actuator'], a)   # wrapper would resolve against its cwd
    _write_refs(a, refs)
    m['assets']['per_world_model_references_sha256'] = pc.file_sha256(a / 'refs.json')
    match = 'outside' if kind == 'outside' else 'normalized absolute path'
    _refused(tmp_path, m, core, match)


@pytest.mark.parametrize('text,match', [
    ('{"%s": {"actuator": "/a", "geometry": "/g"}, "%s": {"actuator": "/b", "geometry": "/h"}}' % (X1, X1),
     'repeats a key'),
    ('{"%s": {"actuator": "/a", "geometry": "/g", "extra": "/e"}}' % X1, 'exactly'),
    ('{"not-a-sha": {"actuator": "/a", "geometry": "/g"}}', 'not a scene XML sha256'),
    ('[]', 'must be an object')])
def test_ambiguous_references_json_is_refused(case, text, match):
    """Formats json.loads + the wrapper would resolve one way while a reader could check another."""
    tmp_path, a, m, _ = case
    core, _ = _core(m)
    (a / 'refs.json').write_text(text)
    m['assets']['per_world_model_references_sha256'] = pc.file_sha256(a / 'refs.json')
    _refused(tmp_path, m, core, match)


def test_relative_references_json_path_is_refused():
    with pytest.raises(ValueError, match='absolute'):
        pc.per_world_reference_files('refs.json')


def test_digest_is_independent_of_json_key_order(case):
    _, a, _, refs = case
    before = pc.per_world_reference_digest(str(a / 'refs.json'))
    _write_refs(a, dict(reversed(list(refs.items()))))
    assert pc.per_world_reference_digest(str(a / 'refs.json')) == before


def test_digest_field_is_a_vm_field_in_the_core():
    m = json.loads((ROOT / 'experiments/2026-10-21-pairact-r1/RUN_MANIFEST.json').read_text())
    assert 'assets.per_world_reference_files_sha256' in pc.VM_FIELDS
    assert 'per_world_reference_files_sha256' in pc.manifest_core(m)['assets']
    assert m['collector']['branch'] == 'dsh/pairact-carry-r1-v8'
