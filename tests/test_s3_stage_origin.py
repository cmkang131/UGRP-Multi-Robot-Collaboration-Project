import copy
import json
import pytest
from sim.s3_stage_origin import OPTION, initialize
from scripts.run_s3_x86_probe import varied_setup, ROOT, FIXTURE
from scripts import run_s3_setdown as previous


@pytest.mark.parametrize('condition', range(6))
def test_rigid_stage_setup_preserves_relative_geometry_and_condition(condition):
    source = varied_setup('pair', condition)
    before = copy.deepcopy(source)
    out = initialize(source, 'pair', [1.3, .05], OPTION)
    assert source == before
    b, a = source['truth']['items']['beam_1'], out['truth']['items']['beam_1']
    assert [a['x'], a['y']] == [1.3, .05]
    for rid in ('r1', 'r2'):
        old, new = source['robots'][rid], out['robots'][rid]
        for i, axis in enumerate(('x', 'y')):
            assert new['pose']['robot_xyz_m'][i]-a[axis] == pytest.approx(old['pose']['robot_xyz_m'][i]-b[axis])
        assert old['pose']['robot_yaw_rad'] == new['pose']['robot_yaw_rad']
        assert old['frame'] == new['frame']
    assert source['robots']['r3'] == out['robots']['r3']
    assert source['truth']['items']['cyan_1'] == out['truth']['items']['cyan_1']
    assert source['offset_body_m_rad'] == out['offset_body_m_rad']
    assert not out['stage_origin_receipt']['runtime_truth_feedback']
    assert not out['stage_origin_receipt']['controller_pose_prior']


def test_off_and_cyan_are_identical_objects_and_invalid_inputs_rejected():
    source = varied_setup('pair', 0)
    assert initialize(source, 'pair', [1.3, .05]) is source
    cyan = varied_setup('cyan', 3)
    assert initialize(cyan, 'cyan', [1.3, .05], OPTION) is cyan
    with pytest.raises(ValueError): initialize(source, 'pair', [1.3, float('nan')], OPTION)
    with pytest.raises(ValueError): initialize(source, 'pair', [1.3, .05], 'unknown')
    assert json.loads((ROOT/FIXTURE).read_text())['cases']['pair']['truth']['items']['beam_1']['x'] == 1.2749148886483785


def test_bundle_preregistration_fixed_goal_and_twenty_cases():
    from scripts.run_s3_stage_origin import bundle, BUNDLE_ID, PLAN
    from scripts.run_s3_stage_origin_cohort import commands
    old = bundle('0'*40, 'pair', 0)
    new = bundle('0'*40, 'pair', 0, OPTION)
    assert old['stage_origin']['option'] == 'off'
    assert new['execution_bundle_id'] == BUNDLE_ID
    assert new['stage_origin']['public_start_xy_m'] == [1.3, .05]
    for key in ('seed', 'provider_seeds', 'controller_config', 'integer_carry', 'setdown'):
        assert old[key] == new[key]
    assert new['integer_carry']['option'] == 'integer_ticks_v1'
    plan = json.loads((ROOT/PLAN).read_text())
    runs = commands(plan, '0'*40)
    assert len(runs) == len({r['name'] for r, _ in runs}) == 20
    for option in ('off', OPTION):
        assert {r['condition'] for r, _ in runs if r['case'] == 'pair' and r['option'] == option} == set(range(6))
        assert {r['condition'] for r, _ in runs if r['case'] == 'cyan' and r['option'] == option} == {0, 3, 4, 5}


def test_outer_runner_rebinds_setup_before_runtime_without_mutating_parent(monkeypatch):
    from scripts import run_s3_stage_origin as runner
    stage = runner.previous.previous.stage
    original = stage.varied_setup
    def inherited_run(b, out):
        return previous.stage.run(b, out)
    def inherited_stage(b, out):
        return varied_setup(b['case'], b['initial_condition'])
    # Exercise both nested function bindings, without creating/stepping physics.
    monkeypatch.setattr(runner.previous, 'run', inherited_run)
    monkeypatch.setattr(stage, 'run', inherited_stage)
    b = dict(case='pair', initial_condition=0,
        stage_origin=dict(option=OPTION, public_start_xy_m=[1.3, .05]))
    out = runner.run(b, None)
    assert out['truth']['items']['beam_1']['x'] == 1.3
    assert stage.varied_setup is original
