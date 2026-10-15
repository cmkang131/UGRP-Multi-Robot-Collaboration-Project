"""Nonphysics input isolation, disturbance labels and exact replay comparisons."""
from copy import deepcopy
import json
from pathlib import Path
import pytest
from harness import grasp_act_contract as c
from harness.grasp_act_data import read_rows, write_json
from harness.beampair_recording import command_identity, make_training_view
from tests.test_grasp_act_data import episode


def make_pair(tmp_path):
    run=tmp_path/'run-1';raw=None
    # Use the tested ACT fixture and preserve separate per-actor source files.
    for rid,role in [('r1','teal'),('r2','blue')]:
        other=tmp_path/rid
        raw0,obs,labels=episode(other,1,robot=rid,role=role,kind='long_beam')
        if raw is None:
            import shutil
            shutil.copytree(raw0,run/'raw');raw=run/'raw'
        else:
            import shutil
            shutil.copytree(raw0/'rgb'/rid,raw/'rgb'/rid)
        previous=obs[0]['issued'][-1]
        for i,(o,l) in enumerate(zip(obs,labels)):
            o['schema']='ugrp.grasp_act.student.v5'
            o['issued']=[deepcopy(previous) for _ in range(c.HISTORY)]
            previous=l['clean_teacher_command']
            l['applied_command']=deepcopy(previous);l['teacher_phase']='complete' if i==4 else 'align'
        for name,data in ((f'student-{rid}.jsonl',obs),(f'teacher-{rid}.jsonl',labels)):
            (raw/name).write_text(''.join(json.dumps(x)+'\n' for x in data))
    result=json.loads((raw/'result.json').read_text());result.update(cap_end=False,
        input_audit=dict(invisible_measurements=0,held_world_reads=0))
    write_json(raw/'result.json',result)
    write_json(raw/'plan.json',dict(seed=1,roles=dict(r1='teal',r2='blue')))
    adapter=run/'adapter';adapter.mkdir()
    write_json(adapter/'beampair1-result.json',dict(training_rgb=True,held_world_reads=0,
        source_sha='b'*40,dependency_sha='a'*40))
    probes=[]
    for rid in ('r1','r2'):
        labels=read_rows(raw/f'teacher-{rid}.jsonl')
        for i,l in enumerate(labels):
            probes.append(dict(robot_id=rid,t=l['clean_teacher_command']['t'],
                issued_command=l['applied_command'],clean_teacher_command=l['clean_teacher_command'],
                disturbance={'test':True} if i==2 else None))
    (adapter/'beampair1-commands.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in probes))
    return run


def test_separate_actors_exact_history_excluded_perturb_and_completion(tmp_path,monkeypatch):
    import harness.beampair_recording as b
    monkeypatch.setattr(b,'camera_config',lambda:dict(schema=c.SCHEMA))
    run=make_pair(tmp_path)
    original=(run/'raw/student-r1.jsonl').read_bytes()
    out=make_training_view(run)
    assert out['admitted'] and len(out['actors'])==2
    assert (run/'raw/student-r1.jsonl').read_bytes()==original
    for rid in ('r1','r2'):
        obs=read_rows(run/f'training/student-{rid}.jsonl')
        labels=read_rows(run/f'training/teacher-{rid}.jsonl')
        assert all(o['robot_id']==rid and o['schema']==c.SCHEMA for o in obs)
        assert all(ref['robot_id']==rid for o in obs for ref in o['rgb'])
        assert labels[2]['perturbation_interval'] and not labels[2]['local_skill_sample']
        assert sum(x['done'] for x in labels)==1
        assert (run/f'raw/rgb/{rid}/0.jpg').stat().st_ino==(run/f'training/rgb/{rid}/0.jpg').stat().st_ino


def test_failed_episode_is_retained_and_never_admitted(tmp_path):
    run=make_pair(tmp_path)
    result=json.loads((run/'raw/result.json').read_text());result['physical_success']=False
    write_json(run/'raw/result.json',result)
    assert not make_training_view(run)['admitted']
    assert not (run/'training').exists() and (run/'raw/student-r1.jsonl').exists()


def test_future_or_foreign_observations_fail_closed(tmp_path,monkeypatch):
    import harness.beampair_recording as b
    monkeypatch.setattr(b,'camera_config',lambda:dict(schema=c.SCHEMA))
    run=make_pair(tmp_path)
    path=run/'raw/student-r1.jsonl';rows=read_rows(path)
    rows[0]['rgb'][0]['robot_id']='r2'
    path.write_text(''.join(json.dumps(x)+'\n' for x in rows))
    with pytest.raises(ValueError,match='own RGB'):make_training_view(run)


def test_identity_detects_single_pwm_difference(tmp_path):
    import shutil
    old=make_pair(tmp_path/'old');new=tmp_path/'new';shutil.copytree(old,new)
    assert command_identity(old,new)['passed']
    path=new/'raw/teacher-r2.jsonl';rows=read_rows(path)
    rows[2]['clean_teacher_command']['pwm']['3']+=1
    path.write_text(''.join(json.dumps(x)+'\n' for x in rows))
    assert not command_identity(old,new)['passed']
