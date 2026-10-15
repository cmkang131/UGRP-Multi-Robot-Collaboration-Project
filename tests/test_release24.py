"""Saved scalar counterexamples and actual clock-only runner; no physics."""
import copy
import json
import math
from pathlib import Path
import pytest
from sim import release23,release24
from sim.failure_rgb_recording import FailureRGB
from tests.test_release23 import reports
from tests.test_grasp_act_release_run import fake_backend  # noqa: F401
from scripts import run_grasp_act_release as runner


def pair(a=(-5.65,-12.10)):
    r=reports([-.02,.72])
    for v,angle in zip(r.values(),a):v['axis_error_rad']=math.radians(angle)
    return r


def choose(r,**opts):
    return release24.pair_choice(r,('r1','r2'),2.,axis_recovery=True,
        margin_common_mode=release23.MARGIN,release_leg_budget=release23.LEG,**opts)


def test_saved_split_10degree_gate_and_consistency():
    r=pair();saved=copy.deepcopy(r)
    a=choose(r,axis_fusion=release24.FUSION)
    assert a['action']=='shift' and math.degrees(a['fused_axis_error_rad'])==pytest.approx(-9.0317096,abs=.002)
    b=choose(r,axis_fusion=release24.FUSION,axis_disagree_reobserve=release24.REOBSERVE)
    assert b['reason']=='axis_disagreement_reobserve' and b['action']=='observe'
    assert b['minimum_gap']<0 and b['blocking_object']
    assert r==saved


def test_true_axis_excess_is_corrected_and_angle_wrap_is_consistent():
    a=choose(pair((12,13)),axis_fusion=release24.FUSION,axis_disagree_reobserve=release24.REOBSERVE)
    assert a['action']=='axis_correct' and min(a['axis_errors_rad'])>math.radians(10)
    b=choose(pair((89,-89)),axis_fusion=release24.FUSION)
    assert abs(math.degrees(b['fused_axis_error_rad']))>89


@pytest.mark.parametrize('mutate',[
    lambda r:r['r2'].update(observation_epoch=2),
    lambda r:r['r2'].update(observed_at=1.1),
    lambda r:r['r1'].update(axis_error_rad=float('nan')),
    lambda r:r['r1'].update(kind='none'),
])
def test_stale_unobserved_nonfinite_pair_never_authorizes_motion(mutate):
    r=pair();mutate(r)
    assert choose(r,axis_fusion=release24.FUSION)['action']=='observe'


def test_off_is_exact_release23_and_no_margin_relaxation():
    r=pair((4,4.2))
    assert choose(r)==release23.pair_choice(r,('r1','r2'),2.,axis_recovery=True,margin_common_mode=release23.MARGIN,release_leg_budget=release23.LEG)
    assert choose(r,axis_fusion=release24.FUSION)['action']!='lower'
    assert release24.AXIS_LIMIT_RAD==math.radians(10)


def test_recording_ring_is_bounded_and_success_does_not_write_frames(tmp_path):
    b=FailureRGB()
    for i in range(201):b.capture(i*.1,{'r1':lambda:b'jpeg'})
    assert len(b.rows)==101
    d=b.finish(tmp_path,failed=True)
    assert d['retained_frames']==101 and d['retained_range_sim_s']==[10,20]
    assert d['bytes']==404
    success=tmp_path/'success';success.mkdir()
    assert b.finish(success,failed=False)['retained_frames']==0


def test_actual_runner_off_preserves_commands_and_trace(tmp_path,fake_backend):
    import ast,subprocess
    src=subprocess.run(['git','show','8d24a525:scripts/run_grasp_act_release.py'],text=True,check=True,stdout=subprocess.PIPE).stdout
    fn=next(n for n in ast.parse(src).body if isinstance(n,ast.FunctionDef) and n.name=='run')
    ns=runner.__dict__.copy();exec(compile(ast.Module(body=[fn],type_ignores=[]),'<release23>','exec'),ns)
    p=json.loads((runner.ROOT/'experiments/2026-10-14-e2e18-grasp-rootcause/release23-dev6-plan.json').read_text())
    world,ports=fake_backend;top=world.render_team_jpeg
    old=ns['run'](p['episodes'][0],tmp_path/'old',cap_s=25,**p['execution_profile'])
    actions={r:copy.deepcopy(v.actions) for r,v in ports.items()}
    world.data.time=0;world.steps=0;world.closed=False;ports.clear();world.render_team_jpeg=top
    new=runner.run(p['episodes'][0],tmp_path/'new',cap_s=25,**p['execution_profile'])
    assert actions=={r:v.actions for r,v in ports.items()}
    for rid in ('r1','r2'):
        assert (tmp_path/'old'/f'teacher-{rid}.jsonl').read_bytes()==(tmp_path/'new'/f'teacher-{rid}.jsonl').read_bytes()
    for k in ('code_decisions','line_rechecks','release_outcome','input_audit'):assert old[k]==new[k]


def test_queue_two_candidates_same_scenes_disabled_and_evidence_required(tmp_path):
    from scripts.prepare_release24_queue import build,verify
    with pytest.raises(ValueError):build('a'*40,tmp_path/'missing')
    p=tmp_path/'table.json';p.write_text('{}');q=build('a'*40,p);verify(q)
    assert len(q['runs'])==12 and not q['approved']
    assert [r['seed'] for r in q['runs'][:6]]==[r['seed'] for r in q['runs'][6:]]
