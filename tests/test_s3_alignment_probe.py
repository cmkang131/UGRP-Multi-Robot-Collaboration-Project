import copy,json,math
from pathlib import Path
import numpy as np
import pytest
from harness.zone_s3_visual_pose_servo import Selector,transform,attach_endpoint
from harness.zone_s3_pair_alignment import project
from harness.zone_solo_cyan_path_heading import command_reason

def profiles():
    p=json.loads(Path('configs/s2_v133_full_template.json').read_text())
    return p['pulse_calibration']['profiles']

def test_full_station_lever_arm_and_rotation_sign():
    q,a=transform([.2032,0],.1,[0,0,.1])
    assert q[1]==pytest.approx(-.2032*math.sin(.1))
    assert a==pytest.approx(0.)

def test_off_does_not_touch_object():
    marker=object();assert attach_endpoint(marker) is marker

def test_existing_v152_last_errors_produce_legal_bounded_plan():
    ps=profiles();s=Selector(ps)
    for e in ([.0187151338,.0020969867,.34871237],[.0165333026,.0054203005,.32604036]):
        a,p,r=s(ps,e)
        assert p and command_reason(a) is None and a['left']==0
        assert r['after']<r['before'] and not r['thresholds_changed']
    assert s(ps,[.5,0,0])==project(ps,[.5,0,0])

def test_actual_s3_selector_binding_and_native_apply(tmp_path,monkeypatch):
    from tests import s3_stage_probe as probe
    from harness import zone_s3_recovery_contract as contract
    from harness.zone_s3_recovery_runtime import Runtime
    from harness.zone_s3_visual_pose_servo import OPTION
    monkeypatch.setattr(probe,'contract',contract);monkeypatch.setattr(probe,'Runtime',Runtime)
    p=probe.Probe(tmp_path,monkeypatch)
    try:
        for rid,ep in p.eps.items():
            attach_endpoint(ep,OPTION)
            p.refresh(1.)
            ep.controller.state='align'
            ob=ep.controller._align.__func__.__globals__['ob']
            command=ob.align_command(dict(grip_base_m=[.2219151338,.0020969867],axis_heading_rad=.34871237))
            ep.controller.drive(command,1.)
            issued=p.drain(ep,1.)
            assert any(a.get('turn') or a.get('forward') for a in issued)
            assert ep.s3_alignment_audit[-1]['phase']=='visual_pose_mpc'
        assert all(command_reason(r) is None for r in p.issued if r['kind']=='mecanum')
    finally:p.runtime.close()

def test_probe_cap_plan_and_population_is_only_change(tmp_path,capsys):
    import importlib.util
    from dataclasses import dataclass,asdict
    from types import SimpleNamespace
    from scripts.run_s3_alignment_probe import main,CAP
    assert CAP==60.
    assert main(['--expected-source-sha','0'*40,'--output',str(tmp_path/'planned')])==0
    assert not (tmp_path/'planned').exists()
    path=Path('experiments/2026-10-09-s3-no-prior/s3fix8/particle_count.py')
    spec=importlib.util.spec_from_file_location('particle_count',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    @dataclass(frozen=True)
    class Options:
        particles:int=100
        seed:int=1234
    module=SimpleNamespace(RBPFOptions=Options)
    m.install_population(module,100);assert module.RBPFOptions is Options
    m.install_population(module,500);assert asdict(module.RBPFOptions())==dict(particles=500,seed=1234)

def test_cyan_orientation_is_not_added_to_existing_alignment_verdict():
    ps=profiles();s=Selector(ps,angle_required=False)
    a,p,row=s(ps,[0,0,math.pi/2])
    assert p is None and row['before']==0
    from harness.zone_s3_visual_pose_servo import attach_solo
    marker=object();assert attach_solo(marker) is marker

def test_no_action_penalty_dead_zone_outside_original_tolerance():
    ps=profiles();s=Selector(ps)
    e=[-.003063845889049094,-.003210532023583606,-.03039554654342916]
    a,p,r=s(ps,e)
    assert p is not None and r['after']<r['before']
