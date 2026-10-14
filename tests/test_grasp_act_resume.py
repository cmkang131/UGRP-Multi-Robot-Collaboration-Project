"""A driver-only continuation cannot silently change the qualified teacher."""
import json,hashlib,shutil
from pathlib import Path
import pytest
from scripts.run_grasp_act_batch import reuse_speed_gate


def test_resume_checks_plan_speed_and_every_changed_execution_path(tmp_path,monkeypatch):
    import scripts.run_grasp_act_batch as module
    root=Path(module.__file__).resolve().parents[1]
    prior=tmp_path/'runs'/'prior';prior.mkdir(parents=True)
    baseline=tmp_path/'src'/'fixed';baseline.mkdir(parents=True)
    names=('sim/grasp_act_teacher.py','sim/grasp_act_scene.py','sim/grasp_act_port.py',
        'scripts/run_grasp_act_teacher.py','scripts/zone_teacher.py','harness/grasp_act_contract.py',
        'harness/visual_arm_v3.py','sim/masterpi_drive_friction_v7.py','configs/simulation_workflows.json')
    for name in names:
        target=baseline/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(root/name,target)
    plan=tmp_path/'plan.json';plan.write_text('{"episodes": []}')
    def write(name,value):(prior/name).write_text(json.dumps(value))
    write('RUN_META.json',{'sha':'fixed'})
    write('resource-admission.json',{'plan_sha256':hashlib.sha256(plan.read_bytes()).hexdigest()})
    write('speed-gate.json',{'admitted':True,'completed':16,'median_wall_per_sim':2.65})
    before={n:'old' for n in (*names,'scripts/run_grasp_act_batch.py')}
    after={**before,'scripts/run_grasp_act_batch.py':'new'}
    monkeypatch.setattr(module,'execution_tree',lambda p:before if p==baseline else after)
    monkeypatch.setattr(module.subprocess,'check_output',lambda *a,**k:'fixed\n')
    _,proof=reuse_speed_gate(prior,plan,16,3.5)
    assert len(proof['identical_components_sha256'])==9
    after['sim/grasp_act_teacher.py']='changed'
    with pytest.raises(ValueError,match='byte-identical'):reuse_speed_gate(prior,plan,16,3.5)
    after['sim/grasp_act_teacher.py']='old';plan.write_text('{}')
    with pytest.raises(ValueError,match='same frozen plan'):reuse_speed_gate(prior,plan,16,3.5)


def test_exact_unfinished_indices_preserve_frozen_plan():
    from scripts.run_grasp_act_batch import selected_indices
    assert selected_indices(40,0,[17,20,*range(32,40)])==[17,20,*range(32,40)]
    assert selected_indices(40,16,None)==list(range(16,40))
    for indices in ([17,17],[40],[-1],[]):
        with pytest.raises(ValueError):selected_indices(40,0,indices)
    with pytest.raises(ValueError):selected_indices(40,16,[17])
