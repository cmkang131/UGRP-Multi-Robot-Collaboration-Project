"""A driver-only continuation cannot silently change the qualified teacher."""
import json,hashlib
from pathlib import Path
import pytest
from scripts.run_grasp_act_batch import reuse_speed_gate


def test_resume_checks_plan_speed_and_every_changed_execution_path(tmp_path,monkeypatch):
    import scripts.run_grasp_act_batch as module
    root=Path(module.__file__).resolve().parents[1]
    plan=tmp_path/'plan.json';plan.write_text('{"episodes": []}')
    def write(name,value):(tmp_path/name).write_text(json.dumps(value))
    write('RUN_META.json',{'sha':'fixed'})
    write('resource-admission.json',{'plan_sha256':hashlib.sha256(plan.read_bytes()).hexdigest()})
    write('speed-gate.json',{'admitted':True,'completed':16,'median_wall_per_sim':2.65})
    changes=['scripts/run_grasp_act_batch.py']
    def git(args,**kwargs):
        if args[1]=='diff':return '\n'.join(changes)
        return (root/args[2].split(':',1)[1]).read_bytes()
    monkeypatch.setattr(module.subprocess,'check_output',git)
    _,proof=reuse_speed_gate(tmp_path,plan,16,3.5)
    assert len(proof['identical_components_sha256'])==9
    changes.append('sim/grasp_act_teacher.py')
    with pytest.raises(ValueError,match='byte-identical'):reuse_speed_gate(tmp_path,plan,16,3.5)
    changes.pop();plan.write_text('{}')
    with pytest.raises(ValueError,match='same frozen plan'):reuse_speed_gate(tmp_path,plan,16,3.5)
