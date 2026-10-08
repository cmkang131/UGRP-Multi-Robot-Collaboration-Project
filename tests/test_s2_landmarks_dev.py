import copy
import json
from types import SimpleNamespace as NS
import pytest
from tests.s2_ci_inputs import portable_s2_inputs

pytestmark = pytest.mark.usefixtures("portable_s2_inputs")
from harness import zone_s2_landmarks_contract as c
from scripts.run_s2_landmarks_dev import start_only_class


def test_admission_seeds_frozen_options_and_physical_gate(tmp_path):
    b=c.bundle('a'*40,'start',sensor_landmarks='floor_zones_doors_v1');c.require_execution(b)
    assert b['task']['seed']==1052 and b['case_cap_s']==30.
    assert b['options']['idle_robot_contacts']=='freeze_v1'
    assert b['options']['particle_sampling']=='kld_global_v1'
    assert c.bundle('a'*40,'start')['options']['sensor_landmarks']=='off'
    for key,value in [('scenario','S3'),('transport','pair'),('research_result',True)]:
        wrong=copy.deepcopy(b);wrong[key]=value
        with pytest.raises(ValueError):c.require_execution(wrong)
    with pytest.raises(ValueError):c.require_execution(c.bundle('a'*40,'start'))
    full=c.bundle('a'*40,'full',sensor_landmarks='floor_zones_doors_v1')
    with pytest.raises(ValueError):c.require_execution(full)
    proof=dict(execution_bundle_id=c.IDS['start'],source_sha='a'*40,options=b['options'],
        start_within_25cm=True,status='STAGE_REACHED_UNQUALIFIED')
    path=tmp_path/'proof.json';path.write_text(json.dumps(proof))
    f=c.bundle('a'*40,'full',sensor_landmarks='floor_zones_doors_v1',
        start_proof=dict(path=str(path),sha256=c.old.hp.base.sha(path)))
    c.require_execution(f)
    assert f['task']['seed']==1051 and f['options']['carry_pose']=='look_ahead_v1'
    assert 'global_localization' not in f['options']
    mutated=copy.deepcopy(f);mutated['options']['idle_robot_contacts']='off'
    with pytest.raises(ValueError):c.require_execution(mutated)
    proof['start_within_25cm']=False;path.write_text(json.dumps(proof))
    with pytest.raises(ValueError):c.require_execution(f)


def test_start_diagnostic_never_emits_first_base_pulse_or_pickup():
    class Fake:
        robot_id='r3';state='scan'
        def step(self,t):return self.next
    r=start_only_class(Fake)();r.next=[('r3',dict(kind='look',pan_pulse=1500))]
    assert r.step(0)==r.next and not r.start_done
    r.state='search_move';r.next=[('r3',dict(kind='mecanum',left=.35))]
    assert r.step(1)==[('r3',dict(kind='hold'))] and r.start_done
    s=start_only_class(Fake)();s.state='align';s.next=[('r3',dict(kind='grip',pulse=1500))]
    assert s.step(2)==[('r3',dict(kind='hold'))] and s.start_done
