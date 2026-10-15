import ast
import copy
import inspect
from pathlib import Path

import pytest

from harness.grasp_act_rollout import InputAudit
from scripts.analyze_grasp_act_act14 import recount
from scripts.run_grasp_act_student import validate_plan


def test_fresh_teacher_start_distribution_is_explicit():
    plan={'seed':91420,'skill':'grasp','object_kind':'cyan','role':'west','robot_id':'r1',
          'target_setup_xy':[0.,0.],'spawns':{'r1':[-1.,0.,.03,0.]}}
    protocol={'closed_loop_seeds':[91420],'train_seeds':[86820],'validation_seeds':[86865]}
    with pytest.raises(ValueError):validate_plan(plan,protocol)
    validate_plan(plan,protocol,teacher_start_v1=True)
    protocol['train_seeds'].append(91420)
    with pytest.raises(ValueError,match='leak'):validate_plan(plan,protocol,teacher_start_v1=True)


def test_funnel_requires_order_and_full_lift_hold():
    def row(t,**changes):
        return dict(t=t,clearance=.02,tilt=0.,forces=[1.,1.],weld=False,
                    station_error_m=.001,yaw_error_rad=0.,**changes)
    values=[row(i/10) for i in range(31)]
    result=recount(values)
    assert result['lift_success'] and all(result['cumulative_run_pass'].values())
    assert not recount(values[:-1])['lift_success']
    bad=copy.deepcopy(values)
    for r in bad:r['station_error_m']=.1
    result=recount(bad)
    assert result['lift_success'] and not any(result['cumulative_run_pass'].values())
    assert recount([])['max_stable_lift_s']==0


def test_worker_cannot_import_evaluation_or_scene():
    root=Path(__file__).resolve().parents[1]
    tree=ast.parse((root/'scripts/grasp_act_student_worker.py').read_text())
    imports=[n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
    assert all(not any(s in (name or '') for s in ('sim','teacher','evaluation','act14')) for name in imports)
    audit=InputAudit().record
    assert all(audit[k]==0 for k in ('invisible_measurements','held_world_reads','top'))


def test_padded_targets_do_not_enter_eval_loss():
    torch=pytest.importorskip('torch')
    from scripts.evaluate_grasp_act_loss import batch_terms,summarize_terms
    from harness import grasp_act_contract as c
    prediction=torch.zeros((1,c.CHUNK,c.ACTION_DIM))
    state=torch.zeros((1,c.CONTEXT_DIM));state[0,c.HISTORY*14]=1.
    batch={'action':prediction.clone(),'action_is_pad':torch.ones((1,c.CHUNK),dtype=torch.bool),'observation.state':state}
    batch['action_is_pad'][0,0]=False
    batch['action'][0,1:]=999.
    stats={'action_mean':[0.]*c.ACTION_DIM,'action_std':[1.]*c.ACTION_DIM}
    result=summarize_terms([batch_terms(prediction,batch,stats,{'grasp':{'positive_fraction':.5}})])
    assert result['valid_actions']==1 and result['movement_l1']==0
    assert result['balanced_done_bce']==pytest.approx(.69314718)
