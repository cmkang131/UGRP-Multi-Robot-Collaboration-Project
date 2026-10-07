"""v128 admission and real runtime wiring; no simulator execution."""
import copy,json
from pathlib import Path
import pytest
from harness import zone_s2_realism_contract_v128 as c
from scripts import run_s2_realism_v128 as runner


def test_one_dev_seed_exact_options_and_explicit_failed_replay_deviation(tmp_path):
    b=c.bundle('a'*40,seed=1051,stage_probe='place',**c.NEW_OPTIONS);c.require_execution(b)
    assert b['replay_admission_pass'] is False and b['options']['stall_recovery']=='off'
    assert b['options']['idle_robot_contacts']=='freeze_v1'
    for seed in (1052,1053):
        x=copy.deepcopy(b);x['task']['seed']=seed
        with pytest.raises(ValueError):c.require_execution(x)
    for key,val in [('slip_detection','off'),('stall_recovery','nav2_progress_v1'),('contact_filter','off')]:
        x=copy.deepcopy(b);x['options'][key]=val
        with pytest.raises(ValueError):c.require_execution(x)
    for key,val in [('scenario','S3'),('transport','pair'),('research_result',True),('replay_admission_pass',True)]:
        x=copy.deepcopy(b);x[key]=val
        with pytest.raises(ValueError):c.require_execution(x)
    x=copy.deepcopy(b);x['intentional_deviation']['approved']=False
    with pytest.raises(ValueError):c.require_execution(x)
    args=runner.parser().parse_args(['--expected-source-sha','a'*40,'--output',str(tmp_path)])
    assert args.slip_detection==args.stall_recovery=='off'
    assert c.old.hp.base.read(c.ROOT/c.REPLAY)['admission_pass'] is False


def test_runtime_uses_slip_with_frozen_baseline_and_preserves_result_failure(tmp_path):
    from harness.zone_solo_cyan_slip_detect import Runtime,SlipBuffer
    from harness.zone_solo_cyan_contract_v106 import MAP_ID,CALIBRATION,CALIBRATION_SHA
    from harness.zone_pair_highpose_exact_speedups import install
    b=c.bundle('a'*40,seed=1051,stage_probe='place',**c.NEW_OPTIONS)
    _,undo=install('v98-exact-v6')
    r=None
    try:
        opts={k:v for k,v in b['options'].items() if k not in ('drive_profile','stagnation_watch','idle_robot_contacts','dev_grasp_policy','eval_camera_trace')}
        r=Runtime(c.old.hp.resolve(MAP_ID)[0],c.ROOT/CALIBRATION,CALIBRATION_SHA,
            **b['task'],**opts,motion_model=b['motion_model'],pulse_calibration=b['pulse_calibration'],
            extrinsic_calibration=b['extrinsic_calibration'],floor_appearance=b['floor_appearance'])
        assert isinstance(r.flow,SlipBuffer) and r.stall_recovery=='off'
        rec=r.record();assert rec['slip_detection']['gt_inputs'] is False
        result=runner.result_record(dict(evaluation={'success':False}),b,rec)
        assert result['replay_admission_pass'] is False and result['slip_detection']['option']=='slip_detect_v1'
    finally:
        if r is not None:r.close()
        undo()
    def no_world(*a,**k):raise RuntimeError('synthetic error, no physics')
    result=runner.run(b,tmp_path/'synthetic',backend_factory=no_world)
    assert result==json.loads((tmp_path/'synthetic/result.json').read_text())
    assert result['status']=='HOST_ERROR' and result['intentional_deviation']['approved']
    assert result['options']==b['options']


def test_workflow_and_registration_identify_the_same_finite_run():
    from sim.workflow_manager import catalog
    entries,_=catalog(c.ROOT)
    assert any(w['id']==c.BUNDLE_ID for w in entries['workflows'])
    plan=json.loads((c.ROOT/c.PLAN).read_text())
    assert all(plan['options'][k]==v for k,v in c.NEW_OPTIONS.items()) and plan['stop_after_this_run']
    assert plan['dev_runs']==[dict(seed=1051,slot='P1-2',stage='place',role='matched_repeated_seed_not_confirmation')]
