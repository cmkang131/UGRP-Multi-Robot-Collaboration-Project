"""COLLECT_PREREG v5 fixes (dsh/pairact-carry-r1-v5): Codex v4 re-review 1-5 + collector carry_success.

Each test is the counterexample of collect-v4-review-20261021 (admission-probe.py / sharding-probe.py) moved
into the suite, plus the carry_success record_error of the gcp2 shard smoke (2026-10-21).  CPU fakes only.
"""
import copy
import json
from pathlib import Path

import pytest

from harness import pairact_collect as pc
from test_pairact_collect import PREREG, TABLE, FakeEpisode, result, runner

FIX = Path(__file__).resolve().parent / 'fixtures' / 'pairact_c5_shardsmoke_20261021'


@pytest.fixture
def prereg():
    return json.loads(PREREG.read_text())


# ------------------------------------------------------------ 6. summary worlds[].carry_success

def _smoke_world(tmp_path, i, carry=None):
    """A real gcp2 -c5 shard-smoke summary world (no carry_success key) + the gcp6 raw of the same seed."""
    s = json.loads((FIX / 'summary-worlds.json').read_text())
    w = dict(s['worlds'][i])
    raw = tmp_path / f'world-{i:03d}' / 'raw'
    raw.mkdir(parents=True)
    r = json.loads((FIX / w['raw']).read_text())
    if carry is not None:
        r['carry_eval'] = dict(r['carry_eval'], success=carry, failure=None if carry else r['carry_eval']['failure'])
        r['carry_success'] = carry
    (raw / 'result.json').write_text(json.dumps(r))
    w['raw'] = str(raw)
    return w, r, dict(status=s['status'], HOST_ERROR=s['HOST_ERROR'], worlds=[w], rejection_table=TABLE)


def _judge(w, summary, seed):
    case = dict(plan=dict(seed=seed, roles=['r1', 'r2']))
    return runner.judge_world(dict(seed=seed, slot=0), case, w, summary, mode='measurement', clean=True,
                              read_rows=pc.read_jsonl)[0]


def test_smoke_summary_without_carry_success_is_not_a_record_error(tmp_path):
    """gcp2 shard smoke: the gcp6 wrapper summary has no worlds[].carry_success -> 25 record_error (v4)."""
    s = json.loads((FIX / 'summary-worlds.json').read_text())
    assert all('carry_success' not in w for w in s['worlds'])
    for i in (0, 1):
        w, r, summary = _smoke_world(tmp_path / 'f', i)
        assert r['carry_eval']['success'] is False
        j = _judge(w, summary, w['seed'])
        assert j['category'] == 'behavior' and j['outcome'] == 'failure' and j['failure_stage'] == 'carry', j
    w, r, summary = _smoke_world(tmp_path / 's', 0, carry=True)
    j = _judge(w, summary, w['seed'])
    assert j['outcome'] == 'success' and j['admitted'], j          # 16 such worlds were record_error in v4


def test_summary_carry_success_that_disagrees_is_still_a_record_error(tmp_path):
    w, r, summary = _smoke_world(tmp_path, 0, carry=True)
    for bad in (False, None):
        j = _judge(dict(w, carry_success=bad), summary, w['seed'])
        assert j['outcome'] == 'record_error' and 'carry_success disagree' in j['reason']
        # v4 left success/admitted True on this record_error: report ks.admitted 16 vs A.text 0/7 (smoke)
        assert j['success'] is False and j['admitted'] is False
    assert _judge(dict(w, carry_success=True), summary, w['seed'])['outcome'] == 'success'


class NoCarryKeyEpisode(FakeEpisode):
    """Root-runner layout as the gcp6 wrapper writes it: worlds[] without carry_success."""

    def __call__(self, cases_path, indices, out):
        code = super().__call__(cases_path, indices, out)
        path = Path(out) / 'summary.json'
        s = json.loads(path.read_text())
        for w in s.get('worlds', []):
            w.pop('carry_success', None)
        path.write_text(json.dumps(s))
        return code


def test_gcp6_wrapper_summary_writes_carry_success_like_the_c5_root():
    src = (Path(__file__).resolve().parents[1] / 'experiments/2026-10-17-beamact5/teacher/'
           'run_warp_flow_teacher_gcp6.py').read_text()
    block = src[src.index('worlds.append(dict(world=i'):]
    block = block[:block.index("raw=str(a.out/f'world-{i:03d}'/'raw')))")]
    assert "carry_success=(raw.get('carry_eval') or {}).get('success')" in block
    assert "carry_failure=(raw.get('carry_eval') or {}).get('failure')" in block


def test_collect_without_summary_carry_success_admits_from_the_result(tmp_path, prereg):
    from test_pairact_collect import make
    ok = lambda s, c: result() if s % 2 else result(success=False)
    runner.run(tmp_path, prereg, 'sha', mode='measurement', noise='off', batch_size=20, max_batches=1,
               make_cases=make(prereg), run_episode=NoCarryKeyEpisode(ok))
    rows = [r for r in pc.read_ledger(tmp_path / 'ledger.jsonl') if r.get('type') == 'attempt']
    assert len(rows) == 20 and not [r for r in rows if r['outcome'] == 'record_error']
    assert sum(r['success'] for r in rows) == sum(r['seed'] % 2 for r in rows) > 0
    assert all(r['summary_carry_success'] is None for r in rows)


# ------------------------------------------------------------ 4. ledger: one committed prefix

def _shard0(tmp_path):
    sdir = runner.shard_dir(tmp_path, 0)
    sdir.mkdir(parents=True)
    led = sdir / 'ledger.jsonl'
    pc.append(led, pc.header('sha', mode='measurement', noise='off', batch_size=20,
                             shard=dict(index=0, count=2, vm='A')))
    return led


PLAN0 = dict(type='batch_planned', batch=0, split='pilot',
             slots=[dict(seed=8343000, bin='B0', split='pilot', slot=0, requeue=False)])


def test_repaired_torn_tail_then_append_merges_again(tmp_path, prereg):
    """sharding-probe repair_after_merge: v4 sealed the torn 8 bytes and refused the repaired ledger."""
    led = _shard0(tmp_path)
    with led.open('a') as f:
        f.write('{"type":')                                   # 8 bytes, no newline (crash mid-append)
    runner.merge(tmp_path, prereg, 'sha', 2)
    meta = json.loads((tmp_path / 'merged' / 'merge.json').read_text())
    assert meta['shard_ledger_bytes']['s00'] == len(led.read_bytes()) - 8      # committed prefix only
    assert pc.repair_ledger(led) == 8
    pc.append(led, PLAN0)
    rep, meta = runner.merge(tmp_path, prereg, 'sha', 2)
    assert meta['planned'] == [0] and meta['shard_ledger_bytes']['s00'] == len(led.read_bytes())


def test_committed_prefix_change_is_still_refused(tmp_path, prereg):
    led = _shard0(tmp_path)
    pc.append(led, PLAN0)
    with led.open('a') as f:
        f.write('{"type": "attempt"')                          # uncommitted tail, ignored by the seal
    runner.merge(tmp_path, prereg, 'sha', 2)
    data = led.read_bytes()
    led.write_bytes(data.replace(b'8343000', b'8343001', 1))  # rewritten committed row
    with pytest.raises(ValueError, match='append-only'):
        runner.merge(tmp_path, prereg, 'sha', 2)
    led.write_bytes(data[:len(data) - 30])                    # shorter than the sealed prefix
    with pytest.raises(ValueError, match='append-only'):
        runner.merge(tmp_path, prereg, 'sha', 2)


def test_valid_json_without_newline_is_uncommitted_for_reader_and_repair(tmp_path):
    """sharding-probe uncommitted_valid_row: v4 read_ledger showed the row, repair_ledger deleted it."""
    h = pc.header('sha', mode='measurement', noise='off', batch_size=20, shard=dict(index=0, count=2, vm='A'))
    torn = tmp_path / 'torn.jsonl'
    torn.write_text(json.dumps(h) + '\n' + json.dumps(PLAN0))
    before = pc.read_ledger(torn)
    assert before == [h]
    assert pc.shard_view({0: before, 1: []}, 2, 1) is None          # batch 0 not planned yet for the view
    pc.repair_ledger(torn)
    assert pc.read_ledger(torn) == before
    pc.append(torn, PLAN0)
    assert pc.read_ledger(torn) == [h, PLAN0]


# ------------------------------------------------------------ 5. completed attempt identity

def test_duplicate_completed_attempt_is_refused_by_merge(tmp_path, prereg):
    """sharding-probe duplicate_attempt: v4 merged a re-appended attempt as N=41 with finished=true."""
    from test_pairact_collect_shard import run_cooperative
    eps = {i: FakeEpisode(lambda s, c: result()) for i in range(2)}
    run_cooperative(tmp_path, prereg, 2, eps, mode='measurement')
    rep, meta = runner.merge(tmp_path, prereg, 'sha', 2)
    assert meta['finished'] and rep['pilot']['attempts'] == 40
    led = runner.shard_dir(tmp_path, 0) / 'ledger.jsonl'
    dup = next(r for r in pc.read_ledger(led) if r.get('type') == 'attempt')
    pc.append(led, copy.deepcopy(dup))
    with pytest.raises(ValueError, match='duplicate attempt'):
        runner.merge(tmp_path, prereg, 'sha', 2)
    assert json.loads((tmp_path / 'merged' / 'report.json').read_text())['pilot']['attempts'] == 40   # not rewritten


def test_attempt_identity_audit(prereg):
    plan = lambda b, seeds, rq=False: dict(type='batch_planned', batch=b, split='train', bin='B0',
                                           slots=[dict(seed=s, bin='B0', split='train', slot=i, requeue=rq)
                                                  for i, s in enumerate(seeds)])
    att = lambda b, slot, seed, rq=False: dict(type='attempt', batch=b, slot=slot, seed=seed, split='train',
                                               bin='B0', requeue=rq)
    hdr = pc.header('sha', mode='training', noise='off', batch_size=20)
    ok = [hdr, plan(0, [1, 2]), att(0, 0, 1), att(0, 1, 2), plan(1, [2], rq=True), att(1, 0, 2, rq=True)]
    assert pc.check_attempt_identity(pc.replay(prereg, ok)) == 3
    for rows, match in ((ok + [att(0, 1, 2)], 'duplicate attempt'),
                        ([hdr, plan(0, [1, 2]), att(0, 0, 2)], 'planned slot'),
                        ([hdr, plan(0, [1]), att(0, 3, 1)], 'planned slot'),
                        ([hdr, plan(0, [1]), att(0, 0, 1), plan(1, [1]), att(1, 0, 1)], 'duplicate attempt')):
        with pytest.raises(ValueError, match=match):
            pc.check_attempt_identity(pc.replay(prereg, rows))


def test_convert_input_refuses_a_duplicated_attempt(tmp_path, prereg):
    from test_pairact_collect import collect
    state, st, _ = collect(tmp_path / 'run', prereg, lambda s, c: result())
    assert state == 'TRAIN'
    rows = pc.read_ledger(tmp_path / 'run' / 'ledger.jsonl')
    first = next(r for r in rows if r.get('type') == 'attempt' and r['admitted'])
    st2 = pc.replay(prereg, rows + [dict(first)])
    with pytest.raises(ValueError, match='duplicate attempt'):
        pc.convert_input(prereg, st2, tmp_path / 'out', prereg_sha='sha', teacher_sha='t' * 40)
    assert not (tmp_path / 'out').exists()


# ------------------------------------------------------------ 1. recording evidence bound to the current core

def _fz():
    import importlib.util
    from test_pairact_collect import ROOT
    spec = importlib.util.spec_from_file_location('pairact_r1_freeze', ROOT / 'scripts/pairact_r1_freeze.py')
    fz = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fz)
    return fz


def _final(prereg):
    from test_pairact_collect import filled_manifest
    pre = dict(prereg, status='FROZEN')
    m = filled_manifest(pre, status='FROZEN')
    return pre, m, pc.core_sha256(pre, m)


def _bind(m, d):
    m['recording_check'].update({k: pc.file_sha256(d / n) for k, n in pc.RECORDING_FILES.items()})


def test_final_refuses_recording_evidence_of_another_core(tmp_path, prereg):
    """admission-probe REPRO recording: check-rows core_sha256 = 0*64 passed v4 final with qualified + hashes."""
    from test_pairact_collect import recording_dir
    pre, m, core = _final(prereg)
    stale, _ = recording_dir(tmp_path / 'a' if (tmp_path / 'a').mkdir() is None else None, core='0' * 64)
    _bind(m, stale)
    with pytest.raises(ValueError, match='another core'):
        pc.check_run_manifest(m, stage='final', prereg=pre, recording_dir=stale)
    good, _ = recording_dir(tmp_path, core=core)
    _bind(m, good)
    assert pc.check_run_manifest(m, stage='final', prereg=pre, recording_dir=good) == core


@pytest.mark.parametrize('edit, match', [
    (lambda d: _edit(d, 'check-rows.json', lambda r: r['probe_source'].update(core_sha256='e' * 64)),
     'probe_source'),
    (lambda d: _edit(d, 'check-rows.json', lambda r: r['probe_source'].update(purpose=pc.PURPOSE_PILOT)),
     'probe_source'),
    (lambda d: _edit(d, 'probe-cases.json', lambda c: c[0]['plan'].update(seed=8343009)), 'probe_cases_sha256'),
    (lambda d: _edit(d, 'check-rows.json', lambda r: r['recorded'][2].update(index=8343009)), 'seeds differ'),
    (lambda d: _edit(d, 'recording-check.json', lambda c: c.update(indices=[8343000, 8343001, 8343009])),
     'recording-check.json indices'),
    (lambda d: _edit(d, 'probe-cases.json', lambda c: c[1].update(candidate='pairact_p2_r13'), rehash=True),
     'candidate'),
])
def test_recording_evidence_chain_probe_source_cases_rows_check(tmp_path, prereg, edit, match):
    from test_pairact_collect import recording_dir
    pre, m, core = _final(prereg)
    d, _ = recording_dir(tmp_path, core=core)
    edit(d)
    _bind(m, d)                                     # the manifest hashes the edited files: only the chain differs
    with pytest.raises(ValueError, match=match):
        pc.check_run_manifest(m, stage='final', prereg=pre, recording_dir=d)


def _edit(d, name, fn, rehash=False):
    value = json.loads((d / name).read_text())
    fn(value)
    (d / name).write_text(json.dumps(value) + '\n')
    if rehash:                                      # keep check-rows' probe_cases_sha256 in step with the edit
        _edit(d, 'check-rows.json', lambda r: r.update(probe_cases_sha256=pc.file_sha256(d / 'probe-cases.json')))


def test_freeze_final_refuses_stale_primary_and_vm_recording(tmp_path, prereg, monkeypatch):
    from test_pairact_collect import G, ROOT, filled_manifest, recording_dir
    fz = _fz()
    monkeypatch.setattr(pc, 'collector_provenance', lambda repo, sha, files: [])
    pp, mp = tmp_path / 'prereg.json', tmp_path / 'manifest.json'
    pp.write_text(PREREG.read_text())
    m = filled_manifest(prereg, status='DRAFT_VM_FILL')
    for k in pc.RECORDING_FIELDS:
        m['recording_check'][k] = '[VM 기입] filled at FROZEN'
    m['sharding'].update(count=3, lag_batches=3, assignment={'gcp6': [0, 1], 'gcp2': [2]})
    mp.write_text(json.dumps(m, indent=2, ensure_ascii=False))
    core = fz.freeze('core', prereg_path=pp, manifest_path=mp, repo=ROOT, collector_sha=G('f'))['core_sha256']
    dirs = {}
    for name, c in (('good', core), ('stale', '0' * 64), ('good_b', core), ('stale_b', '0' * 64)):
        (tmp_path / name).mkdir()
        dirs[name] = recording_dir(tmp_path / name, core=c)[0]
    before = (pp.read_bytes(), mp.read_bytes())
    with pytest.raises(ValueError, match='another core'):
        fz.freeze('final', prereg_path=pp, manifest_path=mp, repo=ROOT, recording_dir=dirs['stale'],
                  expect_core=core, vm_recording_dirs={'gcp2': dirs['good_b']})
    with pytest.raises(ValueError, match='another core'):
        fz.freeze('final', prereg_path=pp, manifest_path=mp, repo=ROOT, recording_dir=dirs['good'],
                  expect_core=core, vm_recording_dirs={'gcp2': dirs['stale_b']})
    assert (pp.read_bytes(), mp.read_bytes()) == before                  # nothing written on refusal
    fin = fz.freeze('final', prereg_path=pp, manifest_path=mp, repo=ROOT, recording_dir=dirs['good'],
                    expect_core=core, vm_recording_dirs={'gcp2': dirs['good_b']})
    assert fin['core_sha256'] == core


def test_check_rows_binding_reads_the_probe_source_ledger(tmp_path, prereg):
    from test_pairact_collect import H, _probe_ledger
    st = _probe_ledger(tmp_path / 'runc', prereg, pc.PURPOSE_PROBE_SOURCE, H('c'))
    seeds = [r['seed'] for r in pc.probe_slots(st)]
    cases = tmp_path / 'probe-cases.json'
    cases.write_text(json.dumps([dict(plan=dict(seed=s), candidate='pairact_p3_collect') for s in seeds]))
    rows = [dict(index=s) for s in seeds]
    b = pc.check_rows_binding(st, H('c'), cases, rows, rows)
    assert b == dict(core_sha256=H('c'), probe_cases_sha256=pc.file_sha256(cases),
                     probe_source=dict(purpose=pc.PURPOSE_PROBE_SOURCE, core_sha256=H('c'), seeds=seeds))
    with pytest.raises(ValueError, match='core_sha256'):
        pc.check_rows_binding(st, H('d'), cases, rows, rows)
    with pytest.raises(ValueError, match='seeds'):
        pc.check_rows_binding(st, H('c'), cases, rows, rows[::-1])
    cases.write_text(json.dumps([dict(plan=dict(seed=s + 1), candidate='pairact_p3_collect') for s in seeds]))
    with pytest.raises(ValueError, match='seeds'):
        pc.check_rows_binding(st, H('c'), cases, rows, rows)
    pilot = _probe_ledger(tmp_path / 'pilot', prereg, pc.PURPOSE_PILOT, None)
    with pytest.raises(ValueError, match='pilot_yield_only'):
        pc.check_rows_binding(pilot, H('c'), cases, rows, rows)


# ------------------------------------------------------------ 2. every file the canonical XML references

def _asset_case(tmp_path, scene, files):
    """wrapper / scene / refs / table under tmp_path/assets + extra files; manifest for that template."""
    from test_pairact_collect import filled_manifest
    a = tmp_path / 'assets'
    for name, data in dict({'wrap.py': '# inert\n', 'scene.xml': scene, 'refs.json': '{}\n', 'table.json': '{}\n'},
                           **files).items():
        (a / name).parent.mkdir(parents=True, exist_ok=True)
        (a / name).write_text(data)
    pins = {role: _repo(tmp_path / role) for role in ('teacher', 'adapter')}       # v5 #3: real pinned sources
    tpl = (f'python {a}/wrap.py --flow beampair --cases {{cases}} --indices {{indices}} --cap-s 60 '
           f'--adapter-source {tmp_path}/adapter --teacher-source {tmp_path}/teacher '
           f'--canonical-xml {a}/scene.xml --per-world-model-references-v1 {a}/refs.json '
           f'--rejection-table {a}/table.json --out {{out}}')
    m = filled_manifest(prereg_core(), template=tpl)
    for role, sha in pins.items():
        m['stack'][role]['sha'] = sha
    m['assets'] = dict(wrapper_sha256=pc.file_sha256(a / 'wrap.py'), canonical_xml_sha256=pc.file_sha256(a / 'scene.xml'),
                       per_world_model_references_sha256=pc.file_sha256(a / 'refs.json'),
                       per_world_reference_files_sha256=pc.per_world_reference_digest(a / 'refs.json'),
                       rejection_table_input_sha256=pc.file_sha256(a / 'table.json'), mesh_assets_sha256={})
    return a, m


def prereg_core():
    return dict(json.loads(PREREG.read_text()), status='FROZEN_CORE')


def _register(m, *paths):
    m['assets']['mesh_assets_sha256'] = {str(p): pc.file_sha256(p) for p in paths}


def test_decoy_mesh_registration_is_refused(tmp_path):
    """admission-probe REPRO mesh: actual.obj (referenced) omitted, decoy.obj registered -> v4 core accepted, and
    then accepted again after actual.obj changed."""
    a, m = _asset_case(tmp_path, '<mujoco><asset><mesh name="actual" file="actual.obj"/></asset></mujoco>\n',
                       {'actual.obj': 'actual\n', 'decoy.obj': 'decoy\n'})
    _register(m, a / 'decoy.obj')
    with pytest.raises(ValueError) as e:
        pc.check_run_manifest(m, stage='core', prereg=prereg_core(), verify_assets=True)
    assert f'misses files the canonical XML references: {a / "actual.obj"}' in str(e.value)
    assert f'lists files the canonical XML does not reference: {a / "decoy.obj"}' in str(e.value)
    _register(m, a / 'actual.obj')
    core = pc.check_run_manifest(m, stage='core', prereg=prereg_core(), verify_assets=True)
    (a / 'actual.obj').write_text('changed after FROZEN_CORE\n')
    with pytest.raises(ValueError, match='mesh_assets_sha256 differs'):
        pc.check_run_manifest(m, stage='core', prereg=prereg_core(), verify_assets=True)
    assert core


SCENE = '''<mujoco>
  <compiler meshdir="meshes" texturedir="tex"/>
  <include file="parts/robot.xml"/>
  <asset>
    <texture name="sky" type="skybox" fileright="r.png" fileleft="l.png" fileup="u.png" filedown="d.png"
             filefront="f.png" fileback="b.png"/>
    <texture name="grid" type="2d" builtin="checker" width="8" height="8"/>
    <hfield name="floor" file="floor.png" size="1 1 .1 .1"/>
    <mesh name="abs" file="ABS"/>
  </asset>
</mujoco>
'''


def test_xml_dependencies_follow_include_compiler_dirs_and_cube_textures(tmp_path):
    other = tmp_path / 'elsewhere' / 'abs.stl'
    other.parent.mkdir()
    other.write_text('abs')
    files = {'parts/robot.xml': '<mujoco><asset><mesh file="arm.obj"/><skin file="arm.skn"/></asset>'
                                '<include file="parts/more.xml"/></mujoco>',
             'parts/more.xml': '<mujoco><asset><texture name="t" file="wood.png"/></asset></mujoco>'}
    a, _ = _asset_case(tmp_path, SCENE.replace('ABS', str(other)), files)
    want = {a / 'parts/robot.xml', a / 'parts/more.xml', a / 'meshes/arm.obj', a / 'meshes/arm.skn',
            a / 'meshes/floor.png', a / 'tex/wood.png', other} | {a / f'tex/{c}.png' for c in 'rludfb'}
    assert set(pc.xml_dependencies(a / 'scene.xml')) == {str(p) for p in want}
    # assetdir sets both dirs; strippath keeps only the file name
    (a / 'flat.xml').write_text('<mujoco><compiler assetdir="all" strippath="true"/>'
                                '<asset><mesh file="x/y/m.obj"/><texture file="z/t.png"/></asset></mujoco>')
    assert set(pc.xml_dependencies(a / 'flat.xml')) == {str(a / 'all/m.obj'), str(a / 'all/t.png')}
    (a / 'loop.xml').write_text('<mujoco><include file="loop.xml"/></mujoco>')
    with pytest.raises(ValueError, match='include cycle'):
        pc.xml_dependencies(a / 'loop.xml')


def test_unregistered_include_and_unparsable_xml_are_refused(tmp_path):
    a, m = _asset_case(tmp_path, '<mujoco><include file="sub.xml"/></mujoco>\n',
                       {'sub.xml': '<mujoco><asset><mesh file="m.obj"/></asset></mujoco>', 'm.obj': 'm'})
    _register(m, a / 'm.obj')
    with pytest.raises(ValueError, match='misses files the canonical XML references: .*sub.xml'):
        pc.check_run_manifest(m, stage='core', prereg=prereg_core(), verify_assets=True)
    _register(m, a / 'm.obj', a / 'sub.xml')
    pc.check_run_manifest(m, stage='core', prereg=prereg_core(), verify_assets=True)
    (a / 'sub.xml').write_text('<mujoco><asset><mesh file="m.obj"/></asset>')        # also a hash change
    with pytest.raises(ValueError, match='canonical XML dependencies unreadable'):
        pc.check_run_manifest(m, stage='core', prereg=prereg_core(), verify_assets=True)


def test_freeze_xml_assets_prints_the_registration(tmp_path):
    a, _ = _asset_case(tmp_path, '<mujoco><asset><mesh file="m.obj"/></asset></mujoco>', {'m.obj': 'm'})
    assert _fz().xml_assets(a / 'scene.xml') == {str(a / 'm.obj'): pc.file_sha256(a / 'm.obj')}


# ------------------------------------------------------------ 3. the checked checkouts are the episode sources

def _repo(path):
    import subprocess
    path.mkdir(parents=True, exist_ok=True)
    git = lambda *a: subprocess.run(['git', '-C', str(path), *a], check=True, capture_output=True, text=True).stdout
    git('init', '-q')
    (path / 'f.txt').write_text(path.name)
    git('add', 'f.txt')
    git('-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qm', 'x')
    return git('rev-parse', 'HEAD').strip()


def _stack(tmp_path, template_roots=None, warp_root_in_template=False):
    """Three real git checkouts pinned in the manifest; the episode template names ``template_roots``."""
    from test_pairact_collect import filled_manifest
    roots = {r: tmp_path / 'src' / r for r in ('teacher', 'adapter', 'root')}
    m = filled_manifest(prereg_core())
    for r, path in roots.items():
        m['stack'][r]['sha'] = _repo(path)
    t = dict(roots, **(template_roots or {}))
    tpl = (f"{'WARP_SOURCE_ROOT=' + str(t['root']) + ' ' if warp_root_in_template else ''}python /w/wrap.py "
           f"--flow beampair --adapter-source {t['adapter']} --teacher-source {t['teacher']} --cases {{cases}} "
           f"--indices {{indices}} --cap-s 60 --rejection-table /abs/table.json --out {{out}}")
    m['command'].update(episode_template=tpl, episode_template_sha256=__import__('hashlib').sha256(tpl.encode()).hexdigest())
    return m, roots


def test_correct_pins_with_other_episode_paths_are_refused(tmp_path):
    """admission-probe v4 remaining R3: real -c5 roots passed check_stack_heads while the episode template named
    /nonexistent teacher / adapter sources."""
    env = dict(WARP_SOURCE_ROOT=str(tmp_path / 'src' / 'root'))
    m, roots = _stack(tmp_path)
    assert pc.check_stack_heads(m, roots, env=env)['teacher'] == m['stack']['teacher']['sha']
    bad, _ = _stack(tmp_path / 'b', dict(teacher='/nonexistent/review-teacher', adapter='/nonexistent/review-adapter'))
    with pytest.raises(ValueError, match='does not exist'):
        pc.check_stack_heads(bad, {r: tmp_path / 'b' / 'src' / r for r in roots}, env=env)
    # an existing checkout at the same pin, but not the one checked
    other = tmp_path / 'copy' / 'teacher'
    other.parent.mkdir()
    __import__('shutil').copytree(roots['teacher'], other)
    m2, _ = _stack(tmp_path / 'c', dict(teacher=other))
    with pytest.raises(ValueError, match='is not the checked teacher checkout'):
        pc.check_stack_heads(m2, {r: tmp_path / 'c' / 'src' / r for r in roots}, env=dict(
            WARP_SOURCE_ROOT=str(tmp_path / 'c' / 'src' / 'root')))


def test_episode_root_source_is_the_checked_root(tmp_path):
    m, roots = _stack(tmp_path)
    with pytest.raises(ValueError, match='WARP_SOURCE_ROOT'):
        pc.check_stack_heads(m, roots, env={})
    with pytest.raises(ValueError, match='is not the checked root checkout'):
        pc.check_stack_heads(m, roots, env=dict(WARP_SOURCE_ROOT=str(roots['teacher'])))
    m2, roots2 = _stack(tmp_path / 'x', warp_root_in_template=True)
    assert pc.check_stack_heads(m2, roots2, env={})['root'] == m2['stack']['root']['sha']    # template wins
    with pytest.raises(ValueError, match='is not the checked root checkout'):
        pc.check_stack_heads(m2, dict(roots2, root=roots['root']), env={})


def test_manifest_gate_checks_the_episode_sources_on_the_vm(tmp_path):
    m, roots = _stack(tmp_path)
    for k in ('wrapper_sha256', 'canonical_xml_sha256', 'per_world_model_references_sha256',
              'rejection_table_input_sha256'):
        m['assets'][k] = 'f' * 64
    def problems(manifest):
        with pytest.raises(ValueError) as e:
            pc.check_run_manifest(manifest, stage='core', prereg=prereg_core(), verify_assets=True)
        return str(e.value)
    assert 'episode --teacher-source' not in problems(m) and 'stack teacher' not in problems(m)
    bad, _ = _stack(tmp_path / 'b', dict(teacher='/nonexistent/review-teacher', adapter='/nonexistent/review-adapter'))
    assert 'episode --teacher-source /nonexistent/review-teacher does not exist' in problems(bad)
    assert 'episode --adapter-source /nonexistent/review-adapter does not exist' in problems(bad)
    m['stack']['adapter']['sha'] = 'd' * 40
    assert f"stack adapter checkout {roots['adapter']} is at" in problems(m)
    (roots['teacher'] / 'f.txt').write_text('dirty')
    assert 'has tracked changes' in problems(m)
