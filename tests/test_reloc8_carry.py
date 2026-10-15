import numpy as np
import pytest
from sim.grasp_act_solo_lookaround import SoloLookaround, Carry5ViewRunner
from harness.active_relocalization import OPTION, LOOK
from tests.test_solo_carry5 import recovery_teacher


def test_carry_toggle_requires_safety_and_view_runner_issues_selected_arm():
    t, m, _ = recovery_teacher()
    with pytest.raises(ValueError):
        SoloLookaround(m.static, ops=t.ops, active_relocalization=OPTION)
    look = SoloLookaround(m.static, ops=t.ops, truth_free_v1=True, command_pose=m.loc,
        carry5=True, carry5_rank_aware_views_v1=True, carry7_robust_recovery_v1=True,
        active_relocalization=OPTION)
    look.arm(); look.start(0., 1500)
    assert look.loc.plan['views'][0]['servo'][3] == LOOK[3]
    issued = []
    look.runner.tick(0., set_servo=lambda p, t:issued.append(p), set_wheels=lambda *a:None,
        wheels_idle=lambda:True, capture=lambda *a:pytest.fail('unsettled capture'))
    assert issued[0][3] == LOOK[3]
    assert not look.accepted_ready


def test_new_plan_reproduces_exact_layouts_and_queue_never_authorizes():
    import json
    from pathlib import Path
    from scripts.prepare_reloc8_carry_queue import prepare8, make_queue
    from scripts.run_solo_grasp_act_teacher import validate_carry
    plan=prepare8()
    old=json.loads(Path('experiments/2026-10-15-map-carry-zone/diagnostic-plan-v7.json').read_text())
    for episode in plan['episodes']:
        validate_carry(episode,enabled=True,training_rgb=False,truth_free=True,lift='solo_lift_lookback_v1',negative=False)
    assert [e['seed'] for e in plan['episodes']]==[93261,93262,93266,*range(93290,93298)]
    for e,p in zip(plan['episodes'][:3],old['episodes'][:3]):
        for k in ('spawns','cargo_pose_m','scenario_id','static_map_sha256','task_start'):
            assert e[k]==p[k]
    q=make_queue(plan,'a'*40)
    assert q['run_count']==11 and q['max_parallel']==1
    for obj in [q,q['coordinator_approval'],*q['runs'],*q['execution_stages'],q['texture_comparison']]:
        assert all(obj[k] is False for k in ('approved','enabled','ready','stage_ready','execute','submitted'))
    assert q['texture_comparison']['code_dependency_connected'] is False


def test_actual_grid_never_accepts_single_rgb_plus_command_prior():
    import json
    from pathlib import Path
    from sim.lookaround_localization import LookaroundLocalizer
    from harness.zone_final_environment import resolve
    fixture=json.loads(Path('tests/fixtures/solo_carry6_rank2.json').read_text())
    loc=LookaroundLocalizer(resolve('zone_wide_two_doors_final_v3')[0],fixture['prior'])
    loc.rank_aware_v1=loc.robust_recovery_v1=True
    loc.active_relocalization=OPTION
    P=np.diag(np.square(fixture['prior_sigma']));loc.own.P=P.copy()
    prior=loc.own.x.copy();rec=dict(t=1.,pan_pulse=1500)
    loc._grid_update([],fixture['features'],rec)
    gate=loc.fix_acceptance([],fixture['features'],[],prior,P)
    assert rec['reloc8_modes']['independent_rgb_views']==1
    assert rec['reloc8_modes']['ambiguous'] and not gate['robust_gate']['accepted']
    assert not gate['accepted']
