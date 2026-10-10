import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from scripts import run_own_route_references as m


def test_registration_full36_same6_and_fixed_budgets(tmp_path):
    jobs=m.jobs(tmp_path)
    assert len(jobs)==len({j['output'] for j in jobs})==36
    assert set(j['seed'] for j in jobs)==set(range(63001,63007))
    assert {j['profile'] for j in jobs}=={'baseline'}
    for j in jobs:
        b=m.bundle(j['seed'],'a'*40,j['condition'],'stage')
        assert b['case_cap_s']==540 and b['phase_budgets_s']=={'B_approach':270.,'return':270.}
        assert b['options']['rbpf_population']=='off'
    assert m.bundle(63001,'a'*40,'combined','smoke_resume')['case_cap_s']==8


def test_every_checkpoint_module_remains_frozen():
    p=json.loads((m.ROOT/'experiments/2026-10-10-own-route-full-budget/batch-plan.json').read_text())
    for name,digest in p['frozen_modules'].items():
        assert hashlib.sha256((m.ROOT/name).read_bytes()).hexdigest()==digest,name


def test_mac_execution_forbidden(tmp_path,monkeypatch):
    monkeypatch.setattr(m.platform,'system',lambda:'Darwin')
    with pytest.raises(RuntimeError,match='ORACLE_ONLY'):m.batch(SimpleNamespace(output=tmp_path))
    with pytest.raises(RuntimeError,match='ORACLE_ONLY'):
        with m.server_slot():pass


def write_fixture(p,commands,xyz):
    p.mkdir(exist_ok=True);(p/'eval_only').mkdir(exist_ok=True)
    trace=[dict(t=100+i*.2,stage='approach',command=c) for i,c in enumerate(commands)]
    truth=[dict(t=100+i*.2,robot_xyz_m=[x,0,0],robot_yaw_rad=i*.01) for i,x in enumerate(xyz)]
    (p/'own-controller.jsonl').write_text('\n'.join(map(json.dumps,trace)))
    (p/'eval_only/trajectory.jsonl').write_text('\n'.join(map(json.dumps,truth)))


def test_early_check_real_motion_not_command_inference(tmp_path):
    write_fixture(tmp_path,[{'forward':.3}]*101,[0]*101)
    r=m.early_check(tmp_path,100,181)
    assert r['displacement_m']==0 and r['frames']==101
    write_fixture(tmp_path,[{'turn':.3}]*101,[0]*101)
    assert m.early_check(tmp_path,100,181)['anomaly']=='turn_only_no_translation'
    write_fixture(tmp_path,[{'forward':.3}]*101,[i*.001 for i in range(101)])
    r=m.early_check(tmp_path,100,181)
    assert r['anomaly'] is None and r['displacement_m']==pytest.approx(.1)


def test_missing_records_failure_not_silently_success(tmp_path):
    assert m.early_check(tmp_path,100,181)['anomaly']=='no_frame_or_sim_progress'


def test_scorer_preserves_blocked_denominator(tmp_path):
    p=m.jobs(tmp_path)
    for j in p:j['status']='BLOCKED_ADMISSION'
    r=m.score_batch(p,tmp_path)
    assert len(r)==36 and all(x['samples']==0 and x['status']=='BLOCKED_ADMISSION' for x in r)
    summary=json.loads((tmp_path/'summary.json').read_text())
    assert len(summary['conditions'])==6
    assert all(g['registered']==6 and g['measured']==0 and g['B_arrived'] is None for g in summary['conditions'].values())


def test_passive_arrival_audit_leaves_all_original_outputs_byte_identical():
    import copy,numpy as np
    from test_goal_route_continuous import fake_controller
    from test_own_traversal_graph import sample
    def make():
        c=fake_controller();c.graph.observe(sample(1));c._entity('B',[0,0],1,1,'x');c._select(1)
        c.current_patches=[{'confirmed_t':1}];c.labels=np.ones((3,3));return c
    a,b=make(),make();rows=[];m.arrival_audit(b,rows)
    for i in range(2,8):
        a._arrival(i,i,np.zeros(3),False);b._arrival(i,i,np.zeros(3),False)
    assert json.dumps(a.snapshot(),sort_keys=True).encode()==json.dumps(b.snapshot(),sort_keys=True).encode()
    assert len(rows)==5 and rows[-1]['reached'] and rows[-1]['reason']=='current_evidence'
