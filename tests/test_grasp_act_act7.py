"""Real pinned archive imports and static setup only; never construct a world."""
from contextlib import contextmanager
import hashlib
import importlib
from importlib.machinery import PathFinder
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
from types import SimpleNamespace

import pytest

from scripts import run_grasp_act_recovery as adapter
from scripts.queue_grasp_act_act7 import build_queue

ROOT=Path(__file__).resolve().parents[1]
RECORD=ROOT/'experiments/2026-10-15-act-train'
PACKAGES=('scripts','sim','harness')


@pytest.fixture(scope='module')
def archive(tmp_path_factory):
    root=tmp_path_factory.mktemp('solo-teacher-6f057f7e-archive')
    data=subprocess.check_output(['git','archive',adapter.TEACHER_SHA,'--',
        *PACKAGES,'configs','maps','calibration'],cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        assert tar.pax_headers['comment']==adapter.TEACHER_SHA
        tar.extractall(root,filter='data')
    # Authenticate every archived source/asset against the pinned Git blobs.
    rows=subprocess.check_output(['git','ls-tree','-r',adapter.TEACHER_SHA,'--',
        *PACKAGES,'configs','maps','calibration'],cwd=ROOT,text=True).splitlines()
    for row in rows:
        metadata,path=row.split('\t');blob=(root/path).read_bytes()
        assert hashlib.sha1(f'blob {len(blob)}\0'.encode()+blob).hexdigest()==metadata.split()[2]
    assert not (root/'.git').exists()
    return root


@pytest.fixture
def archived_dependency(archive,monkeypatch):
    # Archive has no Git metadata. Only replace the checkout identity check;
    # the fixture authenticates all content above. Import machinery stays real.
    def validate(root):assert root==archive
    monkeypatch.setattr(adapter,'validate_dependency',validate)
    return archive


def modules():
    return {k:v for k,v in sys.modules.copy().items() if k.split('.')[0] in PACKAGES}


@pytest.mark.parametrize('raise_inside',[False,True])
def test_every_collision_resolves_to_dependency_and_cached_act_is_restored(archived_dependency,raise_inside):
    root=archived_dependency
    old=importlib.import_module('scripts.zone_teacher')
    assert Path(old.__file__).resolve()==ROOT/'scripts/zone_teacher.py'
    assert not hasattr(old,'proportional_drive')
    before=modules();search=sys.path[:]
    inventory=json.loads((RECORD/'act7-module-collisions.json').read_text())
    # Catch additions/removals instead of silently testing a stale inventory.
    actual={str(p.relative_to(ROOT)) for top in PACKAGES for p in (ROOT/top).rglob('*')
            if p.is_file() and '__pycache__' not in p.parts and (root/p.relative_to(ROOT)).is_file()}
    assert actual=={r['path'] for r in inventory['files']}
    class Stop(Exception):pass
    try:
        with adapter.dependency_modules(root):
            for row in inventory['files']:
                path=Path(row['path'])
                # ACT7 act_blob is historical candidate evidence. Subsequent
                # ACT edits may change it; the scoped dependency must still
                # match the immutable teacher blob and resolve to that file.
                blob=(root/path).read_bytes()
                assert hashlib.sha1(f'blob {len(blob)}\0'.encode()+blob).hexdigest()==row['teacher_blob']
                if path.suffix!='.py':continue
                name='.'.join(path.with_suffix('').parts)
                if path.name=='__init__.py':name='.'.join(path.parent.parts)
                parts=name.split('.')
                package=importlib.import_module(parts[0])
                spec=package.__spec__;spec_path=package.__path__
                # Follow the actual scoped package path, without executing
                # unrelated training/remote/physics modules or their parents.
                for i in range(1,len(parts)):
                    # A path-only lookup avoids executing/registering namespace
                    # parents (e.g. scripts.red_block.experimental).
                    spec=PathFinder.find_spec(parts[i],spec_path)
                    assert spec is not None
                    spec_path=list(spec.submodule_search_locations or [])
                assert spec is not None and Path(spec.origin).resolve()==root/path
                assert row['resolves_from']=='teacher_dependency'
            fresh=importlib.import_module('scripts.zone_teacher')
            assert fresh is not old and callable(fresh.proportional_drive)
            assert Path(fresh.__file__).resolve()==root/'scripts/zone_teacher.py'
            # Branch-only modules must fail rather than fall back through sys.path.
            with pytest.raises(ModuleNotFoundError):importlib.import_module('harness.grasp_act_dart')
            if raise_inside:raise Stop
    except Stop:
        assert raise_inside
    assert modules()==before and sys.path==search
    assert importlib.import_module('scripts.zone_teacher') is old


@pytest.mark.parametrize('recovery_mode',[adapter.MODE,adapter.PULSE_MODE,adapter.PERTURB_MODE])
def test_real_adapter_and_teacher_reach_scene_setup_before_world(archived_dependency,monkeypatch,tmp_path,record_property,recovery_mode):
    pytest.importorskip('mujoco')
    root=archived_dependency;original=adapter.dependency_modules;seen={}
    class BeforeWorld(RuntimeError):pass
    host={'instance':'ugrp-sim-gcp1','machine_type':'n4-highcpu-64'}
    @contextmanager
    def scoped(dependency_root):
        with original(dependency_root):
            identity=importlib.import_module('scripts.grasp_act_host')
            monkeypatch.setattr(identity,'identity',lambda _:host)
            monkeypatch.setattr(identity,'require_run_root',lambda _:None)
            runner=importlib.import_module('scripts.run_solo_grasp_act_teacher')
            # Replace Git metadata only; the archive bytes are authenticated.
            def git(args,**kwargs):
                assert kwargs['cwd']==root
                if args==['git','rev-parse','HEAD']:return adapter.TEACHER_SHA+'\n'
                assert args==['git','status','--porcelain','--untracked-files=no']
                return b''
            monkeypatch.setattr(runner,'subprocess',SimpleNamespace(check_output=git))
            writer=importlib.import_module('scripts.run_grasp_act_teacher')
            monkeypatch.setattr(writer,'compress_logs',lambda _:None)
            world=importlib.import_module('sim.masterpi_drive_friction_v7')
            def stop(scene,**kwargs):
                seen.update(scene=scene,world_kwargs=kwargs)
                teacher=importlib.import_module('sim.grasp_act_solo_teacher')
                look=importlib.import_module('sim.grasp_act_solo_lookaround')
                ops=teacher.primitives()
                instance=teacher.SoloTeacher(plan['kind'],plan['role'],ops.folded,
                    profile='solo_visible_only_v1',held_object_hidden_v1=True,setdown_lookaround_v1=True,
                    lookaround=look.SoloLookaround(scene.config['static_map'],ops=ops,truth_free_v1=True),
                    ops=ops,teacher_stability='align_relook_v1',reach_mode='pad_window_v2',
                    rgb_lift_mode='solo_lift_lookback_v1',solo_lift_lookback_margin_v1=True)
                assert instance.phase=='start'
                seen['teacher_constructed']=True
                for name,module in modules().items():
                    file=getattr(module,'__file__',None)
                    if file:assert Path(file).resolve().is_relative_to(root),(name,file)
                seen['imports']={name:str(Path(module.__file__).resolve().relative_to(root))
                    for name,module in modules().items() if getattr(module,'__file__',None)}
                raise BeforeWorld('import/setup boundary: world construction forbidden')
            monkeypatch.setattr(world,'build_world',stop)
            # Independent tripwires, should a future edit cross the boundary.
            mujoco=importlib.import_module('mujoco')
            def forbidden(*a,**k):pytest.fail('physics/render reached')
            for name in ('mj_step','mj_forward','Renderer'):monkeypatch.setattr(mujoco,name,forbidden)
            planner=importlib.import_module('scripts.make_solo_teacher_plan')
            plan=json.loads((RECORD/'act6-gate-plan.json').read_text())['episodes'][0]
            generated=planner.episode(0,'cyan',8316600,'act6_gate')
            assert all(plan[k]==v for k,v in generated.items())
            yield
    monkeypatch.setattr(adapter,'dependency_modules',scoped)
    monkeypatch.setattr(adapter.platform,'system',lambda:'Linux')
    monkeypatch.setattr(adapter,'source_sha',lambda:'a'*40)
    before=modules();search=sys.path[:]
    plan=json.loads((RECORD/'act6-gate-plan.json').read_text())['episodes'][0]
    noise_path=RECORD/('act9-noise.json' if recovery_mode==adapter.PERTURB_MODE else 'act6-noise.json')
    with pytest.raises(BeforeWorld):
        adapter.run(plan,tmp_path/'run/raw',dependency_root=root,noise_path=noise_path,mode=recovery_mode)
    assert seen['teacher_constructed'] and seen['world_kwargs']['seed']==8316600
    assert seen['scene'].config['setup_only']['spawns']==plan['spawns']
    assert seen['imports']['scripts.zone_teacher']=='scripts/zone_teacher.py'
    record_property('teacher_archive_root',str(root))
    record_property('teacher_imports',json.dumps(seen['imports'],sort_keys=True))
    record_property('physics_steps',0)
    assert modules()==before and sys.path==search
    assert (tmp_path/'run/recovery-commands.jsonl').read_text()==''
    evaluation=tmp_path/'run/recovery-eval-only.jsonl'
    assert evaluation.exists() is (recovery_mode in (adapter.PULSE_MODE,adapter.PERTURB_MODE))
    if evaluation.exists():assert evaluation.read_text()==''


def test_gate_queue_has_disabled_flags_completed_census_and_explicit_seed_reuse():
    q=build_queue('a'*40)
    def walk(value):
        if isinstance(value,dict):
            for key,item in value.items():
                if key in ('approved','enabled','ready','stage_ready','submitted'):assert item is False
                walk(item)
        elif isinstance(value,list):
            for item in value:walk(item)
    walk(q)
    assert q['saved_preflight_jobs']==[] and len(q['jobs'])==1
    gate=q['jobs'][0];assert len(gate['runs'])==40
    assert all(r['source_sha']=='a'*40 and r['name'].startswith('act7-gate-') for r in gate['runs'])
    assert all(r['command'][r['command'].index('--out')+1].endswith(r['name']+'/raw') for r in gate['runs'])
    assert [r['seed'] for r in gate['runs']]==q['seed_reuse']['seeds']
    assert q['seed_reuse']['counts_toward_new_gate'] is False
    census=q['completed_inputs']['completed-census-reference']
    assert census['complete'] and census['N']==50 and census['source_files_verified']==100
    assert not census['rerun'] and len(census['receipts'])==4
    assert all('analyze_grasp_act_stall' not in r['command'] for r in gate['runs'])


def test_runtime_rejects_nonpinned_checkout_before_module_changes():
    before=modules();search=sys.path[:]
    with pytest.raises(ValueError,match='clean pinned'):
        with adapter.dependency_modules(ROOT):pytest.fail('wrong dependency accepted')
    assert modules()==before and sys.path==search
