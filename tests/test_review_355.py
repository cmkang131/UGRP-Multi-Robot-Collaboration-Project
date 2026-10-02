"""Independent PR #355 counterexamples; no renderer, model or live lock writes.

Run against an archive of 54d5e28b (copy this file into its tests directory).
On main before v91 exists the module skips. Strict xfails are outstanding
requirements, not passes; --runxfail reproduces their assertion failures.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

pytest.importorskip('harness.zone_final_pair_fast', reason='requires PR #355 archive')
from harness import zone_final_pair_contract as c
from harness import zone_final_pair_heldout as v90
from harness import zone_final_pair_fast as v91
from scripts import agent_lock as lock
from scripts import run_final_pair_fast as run
from scripts.verify_final_pair_fast_guard import outcome
from sim.final_pair_fast import PhysicsBackend as New
from tests.test_zone_final_pair_review_fixes import fake_guard

BASE = '6f8460ad61ed858025a9e1d5d6ce77d7b92d9b1f'
OLD_LOCK_SHA = '709db3d87e4d2369171aba10ce3c64b7c8be254e2de7115ae608a022b1783dce'


@pytest.mark.xfail(strict=True, reason='R1: same legacy ID records a new lock source hash')
@pytest.mark.parametrize('version,map_id,check', [
    ('v88', case['map_id'], check) for check in c.CHECKS
    for case in {row['map_id']: row for row in c.cases(check)}.values()
] + [('v90', m, v90.CHECK) for m in v90.MAPS])
def test_legacy_registered_source_hash_is_not_substituted(version, map_id, check):
    contract = c if version == 'v88' else v90
    actual = contract.bundle(map_id, check)['source_sha256']['scripts/agent_lock.py']
    # No monkeypatch, ignored key, normalized receipt or successor exemption.
    assert actual == OLD_LOCK_SHA


@pytest.mark.xfail(strict=True, reason='R1: writer bytes change without legacy version increment')
@pytest.mark.parametrize('check', ['calibration-unloaded', 'calibration-loaded', 'calibration-fine'])
@pytest.mark.parametrize('artifact', ['bundle', 'plan'])
def test_legacy_writer_bytes_without_historical_hash_fixture(tmp_path, check, artifact):
    from tests.test_review_352 import BASE_BYTES, args, plan
    from harness.zone_final_pair_excitation import MAP_ID
    value = c.bundle(MAP_ID, check) if artifact == 'bundle' else plan(args(tmp_path, MAP_ID, check))
    blob = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n').encode()
    assert hashlib.sha256(blob).hexdigest() == BASE_BYTES[check][artifact]


def acquire(root, module=lock, *, timing=False):
    return module.acquire(root, owner='claude', branch='claude/exclusive', purpose='exclusive',
                          pid=os.getpid(), expected_minutes=1, timing_sensitive=timing)


def slot(root, name='sim-review355'):
    return lock.acquire_sim_slot(root, slot=name, owner='codex', branch='codex/review-355',
                                 purpose='fixture', pid=os.getpid(), expected_minutes=1)


@pytest.mark.xfail(strict=True, reason='R2: default exclusive physics lock overlaps SIM slots')
@pytest.mark.parametrize('exclusive_first', [True, False])
def test_exclusive_lock_excludes_slots_in_both_orders(tmp_path, exclusive_first):
    first, second = (acquire, slot) if exclusive_first else (slot, acquire)
    first(tmp_path)
    with pytest.raises(RuntimeError):
        second(tmp_path)


@pytest.mark.xfail(strict=True, reason='R2: pinned older lock API cannot see a v91 slot')
def test_pinned_legacy_timing_lock_cannot_enter_existing_slot(tmp_path):
    original = subprocess.check_output(['git', 'show', BASE+':scripts/agent_lock.py'], cwd=c.ROOT)
    old = ModuleType('review355_pinned_lock')
    exec(compile(original, '<pinned agent_lock>', 'exec'), old.__dict__)
    slot(tmp_path)
    with pytest.raises(RuntimeError):
        acquire(tmp_path, old, timing=True)


def pair(monkeypatch, loaded=False):
    old = fake_guard(monkeypatch, loaded=loaded)
    new = New.__new__(New)
    new.__dict__ = copy.copy(old.__dict__)
    new._last_guard_xy, new.saved, new.held = {}, [], []
    new._append = lambda p, row: new.saved.append((p, row))
    new.ports = {r: SimpleNamespace(hold=lambda t, r=r: new.held.append(r), tick=lambda t: None)
                 for r in old.ports}
    return old, new


def open_space(obj):
    obj.scene.config['static_map'] = {'bounds_m': [0., 20., -10., 10.], 'obstacles': [
        {'kind': 'wall', 'center_m': [15., 8.], 'half_extents_m': [.1, .1]}]}


@pytest.mark.parametrize('delta,abort', [(0., False), (-2e-10, True), (2e-10, False)])
def test_full_guard_at_exact_035_margin(monkeypatch, delta, abort):
    old, new = pair(monkeypatch)
    open_space(old)
    old.world.data.geom_xpos[0] = [.75+delta, 0., .1]
    old.world.model.geom_rbound[0] = .4
    a, b = outcome(old), outcome(new)
    assert a == b
    assert bool(a['exception']) is abort
    if delta == 0:
        assert a['minimum_hex'] == (.35).hex()
    if abort:
        assert a['abort_records'] and a['holds'] == ['r1', 'r2']


@pytest.mark.parametrize('displacement,abort', [(.01, False), (np.nextafter(.01, np.inf), True)])
def test_full_guard_at_exact_substep_bound(monkeypatch, displacement, abort):
    old, new = pair(monkeypatch)
    open_space(old)
    old.scene.config['static_map']['bounds_m'][0] = -10.
    old.world.data.geom_xpos[0] = [0., 0., .1]
    for obj in (old, new):
        obj._last_guard_xy['r1'] = np.array([[-displacement, 0.]])
    a, b = outcome(old), outcome(new)
    assert a == b and bool(a['exception']) is abort
    if abort:
        assert a['exception'][1] == 'SUBSTEP_DISPLACEMENT_BOUND_EXCEEDED'


@pytest.mark.parametrize('loaded', [False, True])
@pytest.mark.parametrize('fault,reason', [
    ('nan', 'INVALID_ROBOT_GEOMETRY'),
    ('count', 'COLLECTION_GEOMETRY_CHANGED'),
    ('wall', 'CLEARANCE_ABORT: collection geometry wall margin'),
    ('jump', 'SUBSTEP_DISPLACEMENT_BOUND_EXCEEDED'),
])
def test_full_guard_nan_count_and_loaded_beam(monkeypatch, loaded, fault, reason):
    old, new = pair(monkeypatch, loaded)
    assert outcome(old) == outcome(new)
    index = 2 if loaded else 0
    if fault == 'nan':
        old.world.data.geom_xpos[index, 2] = np.nan
    elif fault == 'count':
        old.world.model.ngeom += 1
    elif fault == 'wall':
        old.world.data.geom_xpos[index, 0] = 2.4
    else:
        old.world.data.geom_xpos[index, 0] += .02
    a, b = outcome(old), outcome(new)
    assert a == b
    # A robot's chassis hits the earlier check; the beam has no chassis check.
    if fault == 'wall' and not loaded:
        reason = 'CLEARANCE_ABORT: static-map wall margin not available'
    assert a['exception'] == ('ValueError', reason)
    assert a['abort_records'] == [('eval_only/clearance_abort.jsonl', {
        't': 0., 'reason': reason, 'static_map_sha256': 'test'})]
    assert a['holds'] == ['r1', 'r2']


@pytest.mark.parametrize('field', ['time', 'qpos', 'qvel'])
def test_precheck_skip_requires_exact_clock_and_joint_state(monkeypatch, field):
    _, obj = pair(monkeypatch)
    d = obj.world.data
    d.qpos, d.qvel, d.xpos = np.zeros(7), np.zeros(6), np.zeros((3, 3))
    snapshot = obj._post_state()
    assert obj._same_post_state(snapshot)
    if field == 'time':
        d.time = np.nextafter(d.time, np.inf)
    else:
        getattr(d, field)[0] = -0.  # Equal numerically, different IEEE bytes.
    assert not obj._same_post_state(snapshot)


def test_stale_slot_requires_explicit_dead_owner_release(tmp_path, monkeypatch):
    slot(tmp_path)
    with pytest.raises(RuntimeError):
        lock.release(tmp_path, owner='claude', name='sim-review355', stale=True)
    monkeypatch.setattr(lock, '_alive', lambda pid: False)
    with pytest.raises(ValueError):
        lock.require_sim_slot(tmp_path, slot='sim-review355', owner='codex', branch='codex/review-355')
    with pytest.raises(RuntimeError):
        slot(tmp_path)
    with pytest.raises(RuntimeError):
        acquire(tmp_path, timing=True)
    lock.release(tmp_path, owner='claude', name='sim-review355', stale=True)
    assert not (tmp_path/'sim-review355').exists()
    acquire(tmp_path, timing=True)


def test_two_maps_same_output_race_rejected_before_second_write(tmp_path, monkeypatch):
    from tests.test_zone_final_pair_fast import fake_host, args
    fake_host(tmp_path, monkeypatch)
    # Simulate another run winning after exists() but before atomic mkdir().
    target = tmp_path/'outputs/same'
    real_usage = run.shutil.disk_usage
    def create_competing_output(path):
        target.mkdir(parents=True)
        (target/'plan.json').write_text('other-map-plan\n')
        return real_usage(path)
    monkeypatch.setattr(run.shutil, 'disk_usage', create_competing_output)
    with pytest.raises(FileExistsError):
        run.main(args(target, v91.MAPS[1])+['--execute', '--lock-owner', 'codex', '--sim-slot', 'sim-first'])
    assert (target/'plan.json').read_text() == 'other-map-plan\n'
    assert sorted(p.name for p in target.iterdir()) == ['plan.json']


def test_criterion_b_rejects_v90_and_v91_before_scoring(tmp_path):
    from scripts import validate_consumer_criterion_b as b
    for version in ('v90', 'v91'):
        folder = tmp_path/version
        folder.mkdir()
        (folder/'bundle.json').write_text(json.dumps({
            'execution_bundle_id': 'zone-final-pair-'+version, 'check': 'calibration-unloaded'}))
        (folder/'result.json').write_text(json.dumps({
            'protocol_complete': True, 'status': 'COLLECTED_UNQUALIFIED'}))
        with pytest.raises(ValueError, match='requires a v88 unloaded collection'):
            b.load_case(folder, b.criterion())


def test_criterion_b_does_not_compare_v88_source_file_hashes(tmp_path):
    from scripts import validate_consumer_criterion_b as b
    from tests.test_consumer_criterion_b import raw_case
    folder, _ = raw_case(tmp_path)
    bundle_path = folder/'bundle.json'
    bundle = json.loads(bundle_path.read_text())
    bundle['source_sha256'] = {'scripts/agent_lock.py': '0'*64}
    bundle_path.write_text(json.dumps(bundle))
    # Acceptance at load_case is only a raw-format audit, NOT criterion B pass.
    assert b.load_case(folder, b.criterion())['source_sha'] == '1'*40


def test_351_does_not_compare_v88_source_file_hashes(tmp_path):
    from scripts import final_pair_calibration_io as raw
    from tests.test_final_pair_calibration_assembly import synthetic_collection, refresh_manifest, write
    from harness.zone_final_pair_excitation import MAP_ID
    root = synthetic_collection(tmp_path, 'unloaded')
    folder = root/MAP_ID
    bundle = json.loads((folder/'bundle.json').read_text())
    bundle['source_sha256']['scripts/agent_lock.py'] = '0'*64
    write(folder/'bundle.json', bundle)
    plan = json.loads((root/'plan.json').read_text())
    plan['bundles_sha256'] = [c.base.digest(bundle)]
    write(root/'plan.json', plan)
    refresh_manifest(folder)
    loaded = raw.load_collection(root, 'unloaded', raw.Inputs())
    assert loaded['bundle']['source_sha256']['scripts/agent_lock.py'] == '0'*64
