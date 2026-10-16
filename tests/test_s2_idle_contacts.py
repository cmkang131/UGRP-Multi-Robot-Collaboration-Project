"""S2 bundle admission and constructor wiring; no simulation/renderer/stepping."""
import copy
import json
from contextlib import nullcontext
from types import SimpleNamespace as NS
import pytest
from harness import idle_robot_contacts_contract as idle
from harness import zone_s2_realism_contract_v118 as c


@pytest.fixture(scope='module')
def candidate():
    # Deliberately no real seed; this module does not reserve or run a probe.
    return c.bundle('a'*40,**c.NEW_OPTIONS)


def test_explicit_profile_default_off_and_no_new_probe(candidate):
    from scripts.run_s2_realism_v118 import parser
    from sim.workflow_manager import catalog
    args=parser().parse_args(['--expected-source-sha','a'*40,'--output','/tmp/no-physical-run'])
    assert args.seed is None and args.idle_robot_contacts=='off'
    assert idle.validate(candidate)=='freeze_v1'
    assert candidate['options'].get('roller_collision','mesh')=='mesh'
    assert candidate['comparison_metrics']==['wall_per_sim'] and not candidate['pool_with_previous_s2']
    assert candidate['task']['seed'] is None
    assert 'sim/s2_idle_contacts.py' in candidate['source_sha256']
    assert 'harness/idle_robot_contacts_contract.py' in candidate['source_sha256']
    assert any(w['id']==c.BUNDLE_ID and w['version']=='7.11.0' for w in catalog(c.ROOT)[0]['workflows'])
    with pytest.raises(ValueError,match='NO_S2_DEV_RUN_ADMITTED'):c.require_execution(candidate)
    b=copy.deepcopy(candidate);b['options']['idle_robot_contacts']='off'
    with pytest.raises(ValueError,match='requires all explicit'):c.require_execution(b)
    b['options']['idle_robot_contacts']='always'
    with pytest.raises(ValueError,match='UNKNOWN_OPTION'):idle.validate(b)
    b=copy.deepcopy(candidate);b['task']['seed']=1042
    with pytest.raises(ValueError,match='EXISTING_OR_PREREGISTERED'):c.require_execution(b)
    b['task']['seed']=1029
    with pytest.raises(ValueError,match='EXISTING_OR_PREREGISTERED'):c.require_execution(b)


@pytest.mark.parametrize('changes',[
    {'scenario':'S3'}, {'execution_bundle_id':'zone-s3-three-robot-v107'},
    {'transport':'pair'}, {'cargo':'beam'}, {'active_robot_ids':['r1','r3']},
    {'research_result':True}, {'confirmation_sample':True}, {'preregistered_run':True},
    {'cohort_role':'CONFIRMATORY'}, {'dev_light':False}, {'admission':'research'},
    {'schema':'ugrp.zone_study_bundle.v1'}, {'preregistered_run':None},
])
def test_foreign_pair_research_and_preregistered_bundles_rejected(candidate,changes):
    b=copy.deepcopy(candidate);b.update(changes)
    with pytest.raises(ValueError,match='S2_SOLO_EXPLORATORY_DEV_ONLY'):idle.validate(b)
    b['options']['idle_robot_contacts']='off';before=json.dumps(b).encode()
    assert idle.validate(b)=='off' and json.dumps(b).encode()==before


def test_extra_actor_and_sphere_option_cannot_hide_in_s2_label(candidate):
    b=copy.deepcopy(candidate);b['task']['robot_ids']=['r1','r3']
    with pytest.raises(ValueError,match='S2_SOLO'):idle.validate(b)
    b=copy.deepcopy(candidate);b['options']['roller_collision']='sphere6_v1'
    with pytest.raises(ValueError,match='S2_SOLO'):idle.validate(b)


def test_actual_constructor_binding_record_reset_and_restore(candidate,tmp_path,monkeypatch):
    # The real binding imports MuJoCo, although this fixture never creates or
    # steps a world. Also run in the CI job with simulator dependencies.
    pytest.importorskip('mujoco')
    from sim import s2_realism_camera_binding as camera
    from sim.s2_idle_contacts import backend_class
    calls=[]
    def build(*args,**kwargs):
        calls.append(kwargs)
        mode=kwargs.get('idle_robot_contacts','off')
        return NS(physics_lock=nullcontext(),controllers={},idle_robot_contacts=mode,
                  roller_collision=kwargs.get('roller_collision','mesh'),
                  drive_profile_record={'idle_robot_contacts':mode} if mode!='off' else {})
    monkeypatch.setattr(camera,'build_world',build)
    class Base:
        def __init__(self,bundle,out,**kwargs):
            self.bundle,self.out=bundle,out
            self.world=camera.bound_world('fixture-scene',drive_profile='masterpi_drive_friction_v7')
        def reset(self,cap):return 1.3
        def close(self):pass
    cls=backend_class(Base)
    b=cls(candidate,tmp_path/'on')
    assert calls[-1]['idle_robot_contacts']=='freeze_v1' and calls[-1]['roller_collision']=='mesh'
    assert camera.build_world is build and b.reset(5.)==1.3
    record=json.loads((tmp_path/'on/eval_only/idle-contacts-option.json').read_text())
    assert record['option']=='freeze_v1' and record['controller_feedback'] is False
    off=copy.deepcopy(candidate);off['options']['idle_robot_contacts']='off'
    a=Base(off,tmp_path/'base');base_call=json.dumps(calls[-1]).encode()
    b=cls(off,tmp_path/'off');assert json.dumps(calls[-1]).encode()==base_call
    assert b.reset(5.)==a.reset(5.) and not (tmp_path/'off').exists()
    class Broken(Base):
        def __init__(self,*a,**kw):raise RuntimeError('fixture failure')
    with pytest.raises(RuntimeError,match='fixture failure'):backend_class(Broken)(candidate,tmp_path/'error')
    assert camera.build_world is build
    bad=copy.deepcopy(candidate);bad['scenario']='S3';before=len(calls)
    with pytest.raises(ValueError,match='S2_SOLO'):cls(bad,tmp_path/'foreign')
    assert len(calls)==before


def test_writer_preserves_explicit_option_and_separate_condition(candidate,tmp_path,monkeypatch):
    from scripts import run_s2_realism_v118 as runner
    # Mock only admission for a synthetic IO failure test; no seed is executed.
    monkeypatch.setattr(c,'require_execution',lambda value:idle.validate(value))
    def no_world(*a,**kw):raise RuntimeError('synthetic IO test; no physics')
    result=runner.run(candidate,tmp_path/'synthetic',stage='pick',backend_factory=no_world)
    saved=json.loads((tmp_path/'synthetic/result.json').read_text())
    assert result==saved
    assert saved['execution_bundle_id']=='zone-s2-realism-v118'
    assert saved['options']['idle_robot_contacts']=='freeze_v1'
    assert saved['comparison_metrics']==['wall_per_sim'] and saved['pool_with_previous_s2'] is False
    assert saved['status']=='HOST_ERROR' and saved['model_calls']==0
