import numpy as np
import pytest
import json

from scripts.diagnose_grasp_act_act15 import command_errors, distribution


def test_decode_boundary_is_visible_in_error_metrics():
    target = np.array([.35]*4+[2/3]*4+[0.]*5+[0.])
    prediction = target.copy(); prediction[:4] = .15
    errors = command_errors(prediction, target)
    assert errors['wheel_sign_mismatch'] == 1.
    assert errors['wheel_mae'] == .35
    assert errors['pulse_mae_ms'] == pytest.approx(100.)
    assert errors['pwm_mae'] == 0.
    assert distribution([errors])['wheel_mae']['p95'] == .35


def test_initial_coverage_does_not_admit_exogenous_actions(tmp_path):
    from tests.test_grasp_act_data import episode
    from harness.grasp_act_data import paired_segments
    _, obs, labels = episode(tmp_path, 1)
    obs, labels = obs[:4], labels[:4]
    for i, label in enumerate(labels):
        label.update(local_skill_sample=i==3, teacher_phase=('start','fold','approach','align')[i])
    assert sum(map(len, paired_segments(obs,labels))) == 1
    groups=paired_segments(obs,labels,include_initial_approach_v1=True)
    assert sum(map(len, groups)) == 4
    assert labels[0]['local_skill_sample'] is False
    labels[1].update(perturbation_interval=True)
    groups=paired_segments(obs,labels,include_initial_approach_v1=True)
    assert sum(map(len, groups)) == 3
    assert [len(g) for g in groups] == [1,2]


def test_dagger_aggregation_uses_actual_student_history_and_only_valid_labels(tmp_path):
    from tests.test_grasp_act_data import episode, protocol
    from harness.grasp_act_data import convert, write_json, GraspDataset
    from harness.grasp_act_rollout import OwnHistory
    from scripts.aggregate_grasp_act_act15 import aggregate
    raw, _, _ = episode(tmp_path,1)
    episode(tmp_path,2)
    convert(tmp_path,protocol(),tmp_path/'base')
    run=tmp_path/'collect';raw2=run/'raw';raw2.mkdir(parents=True)
    initial={'t':1.,'wheels':[0.]*4,'duration_s':[0.]*4,'pwm':{str(s):1500 for s in (1,3,4,5,6)}}
    history=OwnHistory('r1','dagger-3',initial)
    jpeg=(raw/'rgb/r1/0.jpg').read_bytes();observations=[];labels=[];commands=[]
    for i in range(5):
        now=1.+i*.1
        obs,_,rel=history.observe(now,jpeg,skill='grasp',object_kind='cyan',role='west',destination_zone='none')
        (raw2/rel).parent.mkdir(parents=True,exist_ok=True);(raw2/rel).write_bytes(jpeg)
        value={**initial,'t':now};history.issue(value)
        observations.append(obs);commands.append({'command':value})
        labels.append({'sample_id':obs['sample_id'],'t':now,'label_valid':i<3,
                       'teacher_phase':'approach' if i<3 else 'hover','teacher_command':value})
    for name,rows in [('student-inputs',observations),('commands',commands),('shadow-labels',labels)]:
        (raw2/(name+'.jsonl')).write_text(''.join(json.dumps(r)+'\n' for r in rows))
    write_json(raw2/'summary.json',{'status':'complete','complete':True,'seed':3})
    write_json(raw2/'plan.json',{'seed':3})
    write_json(raw2/'shadow-progress.json',{'rows':5,'teacher_actions_executed':0,
        'input_audit':{'invisible_measurements':0,'held_world_reads':0}})
    result=aggregate(tmp_path/'base',[run],tmp_path/'combined')
    assert result['rows']=={'train':7,'validation':4}
    assert len(GraspDataset(tmp_path/'combined','train'))==7
    assert json.loads((tmp_path/'base/manifest.json').read_text())['protocol']['train_seeds']==[1]
    with np.load(tmp_path/'combined/3-r1/tensors.npz') as tensors:
        assert tensors['action_is_pad'][-1].tolist()==[False]+[True]*7
        assert not tensors['action'][...,-1].any()
