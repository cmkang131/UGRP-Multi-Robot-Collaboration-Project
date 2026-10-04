"""Evaluation-only NEES of the v98 HIGH checkpoint receipts ("σ 예산 영수증"), simulator-free.

The scorer (``scripts/eval_highpose_receipt_nees.py``) reads eval-only truth after the run; it must never reach
control. Tests: known NEES values on synthetic records, yaw wrap, skipped/undefined receipts, strict JSON, the
frame convention against a recorded run, no harness import of the scorer, and the runner hook (a scorer error
never changes the run status).
"""
from __future__ import annotations

import ast
import json
import math
from pathlib import Path

import numpy as np
import pytest

from harness import zone_pair_highpose_dr_checkpoint as dc
from scripts import eval_highpose_receipt_nees as sc

ROOT = Path(__file__).resolve().parents[1]
FRAME_FIXTURE = Path(__file__).with_name('fixtures')/'v98_receipt_nees_frame_check_1f7fb800.json'


def rot(yaw):
    c, s = math.cos(yaw), math.sin(yaw)
    return [[c, -s, 0.], [s, c, 0.], [0., 0., 1.]]


def write_truth(out, rid, rows):
    """rows: (t, x, y, yaw) -> eval_only/<rid>/camera_labels.jsonl in the backend's field layout."""
    path = Path(out)/'eval_only'/rid/'camera_labels.jsonl'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w') as f:
        for t, x, y, yaw in rows:
            f.write(json.dumps({'t': t, 'frame_id': 1, 'base_position_m': [x, y, .0324],
                                'base_rotation': rot(yaw), 'requested_check': 'carry'}) + '\n')


def truth_grid(x, y, yaw, t0=18., t1=22.):
    n = int(round((t1 - t0)/.05)) + 1
    return [(t0 + i*.05, x, y, yaw) for i in range(n)]


COV = [[.01**2, 0., 0.], [0., .01**2, 0.], [0., 0., .1**2]]


def receipt(event=dc.DR_EVENT, *, rid='r1', t_est=19.84, x=1., y=.5, yaw=.1, cov=COV, seg=1, **extra):
    e = {'robot_id': rid, 'event': event, 'sim_s': t_est + .16, 'seg': seg, 'high': True, 'opened': False,
         'epoch': 1, 'std_xy_m': .0141, 'std_yaw_rad': .1, 'fix_t': None, 'fix_age_s': None,
         'fix_receipt_voided': True, 'report_t_est': t_est, 'stop_s': 1.3,
         'x_m': x, 'y_m': y, 'yaw_rad': yaw, 'cov': cov}
    e.update(extra)
    return e


def run_dir(tmp_path, events_by_rid, truth=None, name='run'):
    out = tmp_path/name
    out.mkdir()
    record = {'pair': [{'robots': {rid: {'events': evs, 'inputs': []} for rid, evs in events_by_rid.items()}}],
              # executor-level events of the same name must never be read as receipts
              'robots': {rid: {'events': [{'event': dc.DR_EVENT, 'x_m': 9.}]} for rid in events_by_rid}}
    (out/'student_record.json').write_text(json.dumps(record))
    for rid, rows in (truth or {}).items():
        write_truth(out, rid, rows)
    return out


@pytest.fixture
def mk(tmp_path):
    """mk(events_by_rid, truth) -> a fresh run dir (several per test)."""
    count = [0]

    def make(events, truth=None):
        count[0] += 1
        return run_dir(tmp_path, events, truth, name=f'run{count[0]}')
    return make


def nees2(ex, ey, a, b, d):
    return (d*ex*ex - 2*b*ex*ey + a*ey*ey)/(a*d - b*b)


# --------------------------------------------------------------------------------------------- constants


def test_chi_square_constants_match_scipy():
    stats = pytest.importorskip('scipy.stats')
    for df in (2, 3):
        assert math.isclose(sc.CHI2[df]['p95'], stats.chi2.ppf(.95, df), rel_tol=1e-12)
        assert math.isclose(sc.CHI2[df]['p999'], stats.chi2.ppf(.999, df), rel_tol=1e-12)
    assert math.isclose(sc.CHI2[2]['p999'], -2*math.log(1 - .999), rel_tol=1e-12)     # df=2 closed form
    assert sc.SCHEMA == 'ugrp.v98.receipt_nees.eval_only.v1'


def test_the_receipt_is_named_a_sigma_budget_receipt_not_accuracy_evidence(tmp_path):
    out = run_dir(tmp_path, {'r1': [receipt()]}, {'r1': truth_grid(1., .5, .1)})
    res = sc.receipt_nees(out)
    assert res['receipt_name'] == 'σ 예산 영수증' and res['receipt_name_en'] == 'sigma-budget receipt'
    assert res['evaluation_only'] is True and res['fed_to_control'] is False
    assert 'EVALUATION ONLY' in res['note'] and 'NOT accuracy' in res['note'] and 'Never fed to control' in res['note']
    assert 'Bar-Shalom' in res['reference'] and '미확인' in res['reference']


# --------------------------------------------------------------------------------------------- NEES values


def test_known_nees_xy_and_pose(mk):
    # error (0.02, 0, 0) at sigma 0.01 -> 4.0 in both; then add a yaw error of 0.2 rad at sigma 0.1 -> pose 8.0
    out = mk({'r1': [receipt()]}, {'r1': truth_grid(1.02, .5, .3)})
    row = sc.receipt_nees(out)['receipts'][0]
    assert row['status'] == 'SCORED' and row['receipt'] == 'dr_budget'
    assert math.isclose(row['nees_xy_2dof'], 4., rel_tol=1e-9) and math.isclose(row['nees_pose_3dof'], 8., rel_tol=1e-9)
    assert math.isclose(row['error_x_m'], .02, abs_tol=1e-12) and row['error_y_m'] == pytest.approx(0, abs=1e-12)
    assert math.isclose(row['error_yaw_rad'], .2, abs_tol=1e-12) and math.isclose(row['error_xy_m'], .02, abs_tol=1e-12)
    assert row['xy_above_chi2_95'] is False and row['xy_above_chi2_99_9'] is False
    assert row['pose_above_chi2_95'] is True and row['pose_above_chi2_99_9'] is False      # 8.0 > 7.81, < 16.27
    assert (row['sigma_x_m'], row['sigma_y_m'], row['sigma_yaw_rad']) == pytest.approx((.01, .01, .1))
    assert row['reported_std_xy_m'] == .0141                                               # the filter's own sigma, logged


def test_correlated_covariance_uses_the_full_inverse(mk):
    cov = [[4e-4, 1e-4, 2e-5], [1e-4, 9e-4, -3e-5], [2e-5, -3e-5, 1e-2]]
    out = mk({'r1': [receipt(cov=cov, x=2., y=-1., yaw=-.2)]},
                  {'r1': truth_grid(2.03, -.98, -.25)})
    row = sc.receipt_nees(out)['receipts'][0]
    assert math.isclose(row['nees_xy_2dof'], nees2(.03, .02, 4e-4, 1e-4, 9e-4), rel_tol=1e-9)
    e = np.array([.03, .02, -.05])
    assert math.isclose(row['nees_pose_3dof'], float(e @ np.linalg.inv(np.array(cov)) @ e), rel_tol=1e-9)
    assert row['nees_pose_3dof'] > 0 and row['nees_xy_2dof'] > 0


def test_yaw_error_is_wrapped_across_pi(mk):
    # estimate +3.13 rad, truth -3.13 rad: the true error is +0.0232 rad, not -6.26 rad
    out = mk({'r1': [receipt(yaw=3.13)]}, {'r1': truth_grid(1., .5, -3.13)})
    row = sc.receipt_nees(out)['receipts'][0]
    assert math.isclose(row['error_yaw_rad'], 2*math.pi - 6.26, abs_tol=1e-12)
    assert math.isclose(row['nees_pose_3dof'], ((2*math.pi - 6.26)/.1)**2, rel_tol=1e-9) and row['nees_pose_3dof'] < .1
    # the other way round
    out = mk({'r1': [receipt(yaw=-3.13)]}, {'r1': truth_grid(1., .5, 3.13)})
    assert sc.receipt_nees(out)['receipts'][0]['error_yaw_rad'] == pytest.approx(-(2*math.pi - 6.26), abs=1e-12)


def test_over_confident_receipt_is_far_above_the_chi_square_bounds(mk):
    # the failure mode this scorer exists for: reported sigma 5 mm, true error 150 mm
    cov = [[.005**2, 0., 0.], [0., .005**2, 0.], [0., 0., math.radians(.5)**2]]
    out = mk({'r1': [receipt(cov=cov)]}, {'r1': truth_grid(1.15, .5, .1)})
    res = sc.receipt_nees(out)
    row = res['receipts'][0]
    assert math.isclose(row['nees_xy_2dof'], (.15/.005)**2, rel_tol=1e-9)
    assert row['xy_above_chi2_99_9'] is True and row['pose_above_chi2_99_9'] is True
    assert res['summary']['xy_above_chi2_99_9_count'] == 1 and res['summary']['max_nees_xy_2dof'] == pytest.approx(900.)


# --------------------------------------------------------------------------------------------- time matching


def test_truth_row_nearest_in_time_and_the_gap_is_recorded(mk):
    rows = [(t, 1. + .1*(t - 19.), .5, .1) for t in np.arange(18., 22.0001, .05)]
    out = mk({'r1': [receipt(t_est=19.84)]}, {'r1': rows})
    row = sc.receipt_nees(out)['receipts'][0]
    assert row['truth_t'] == pytest.approx(19.85) and row['truth_gap_s'] == pytest.approx(.01, abs=1e-9)
    assert row['truth_gap_flag'] is False
    assert row['error_x_m'] == pytest.approx(1.085 - 1., abs=1e-9)                # x at t=19.85
    # report time outside the truth: the gap is large and flagged, the receipt is still scored
    out = mk({'r1': [receipt(t_est=40.)]}, {'r1': rows})
    row = sc.receipt_nees(out)['receipts'][0]
    assert row['status'] == 'SCORED' and row['truth_gap_flag'] is True and row['truth_gap_s'] < -17.


# --------------------------------------------------------------------------------------------- receipt kinds, skips


def test_fix_dr_and_over_receipts_are_all_scored_per_robot(mk):
    events = {'r1': [receipt(dc.FIX_EVENT, seg=1, fix_t=19.84, fix_receipt_voided=False), receipt(dc.DR_EVENT, seg=2)],
              'r2': [receipt(dc.OVER_EVENT, rid='r2', seg=1)]}
    out = mk(events, {'r1': truth_grid(1.02, .5, .1), 'r2': truth_grid(1.1, .5, .1)})
    res = sc.receipt_nees(out)
    assert [(r['robot_id'], r['receipt'], r['seg']) for r in res['receipts']] == [
        ('r1', 'fix', 1), ('r1', 'dr_budget', 2), ('r2', 'over_budget', 1)]
    assert all(r['status'] == 'SCORED' for r in res['receipts'])
    s = res['summary']
    assert s['receipt_count'] == 3 and s['scored_count'] == 3 and s['skipped_count'] == 0
    assert s['by_receipt'] == {'dr_budget': 1, 'fix': 1, 'over_budget': 1}
    assert math.isclose(s['max_nees_xy_2dof'], 100., rel_tol=1e-9)                # r2: 0.1 m at 0.01 m sigma
    assert set(res['truth_files']) == {'r1', 'r2'} and len(res['source']['student_record_sha256']) == 64
    assert all(len(v['sha256']) == 64 for v in res['truth_files'].values())


def test_only_pair_controller_events_are_receipts(mk):
    out = mk({'r1': [receipt()]}, {'r1': truth_grid(1., .5, .1)})
    res = sc.receipt_nees(out)           # run_dir() also planted a same-named event with x_m=9 in record['robots']
    assert res['summary']['receipt_count'] == 1 and res['receipts'][0]['error_x_m'] == pytest.approx(0, abs=1e-12)


def test_receipts_without_estimate_or_truth_are_skipped_not_errors(mk):
    old = receipt()
    for k in ('x_m', 'y_m', 'yaw_rad', 'cov'):
        old.pop(k)                                                                  # record from before the log-only fields
    events = {'r1': [old, receipt(cov=None), receipt(x=None)], 'r2': [receipt(rid='r2')]}
    out = mk(events, {'r1': truth_grid(1., .5, .1)})          # r2 has no camera_labels
    res = sc.receipt_nees(out)
    assert [r['status'] for r in res['receipts']] == ['NO_ESTIMATE_IN_RECEIPT']*3 + ['NO_TRUTH']
    s = res['summary']
    assert s['receipt_count'] == 4 and s['scored_count'] == 0 and s['max_nees_xy_2dof'] is None
    assert 'r2' not in res['truth_files']


def test_undefined_nees_does_not_hide_the_other_receipts(mk):
    zero = [[0., 0., 0.], [0., 0., 0.], [0., 0., 0.]]
    xy_only = [[1e-4, 0., 0.], [0., 1e-4, 0.], [0., 0., 0.]]         # yaw variance 0 (e.g. rounded away): pose undefined
    events = {'r1': [receipt(cov=zero), receipt(cov=xy_only, seg=2), receipt(seg=3)]}
    out = mk(events, {'r1': truth_grid(1.01, .5, .1)})
    res = sc.receipt_nees(out)
    a, b, c = res['receipts']
    assert a['status'] == 'SCORED' and a['nees_xy_2dof'] is None and a['nees_xy_error'] == 'cov_not_positive_definite'
    assert a['nees_pose_3dof'] is None and a['xy_above_chi2_99_9'] is None
    assert math.isclose(b['nees_xy_2dof'], 1., rel_tol=1e-9) and b['nees_pose_3dof'] is None
    assert b['nees_pose_error'] == 'cov_not_positive_definite'
    assert math.isclose(c['nees_xy_2dof'], 1., rel_tol=1e-9)
    assert res['summary']['undefined_nees_count'] == 1 and res['summary']['max_nees_xy_2dof'] == pytest.approx(1.)


def test_a_malformed_receipt_is_a_score_error_row_only(mk):
    events = {'r1': [receipt(cov=[[1., 2.], [3.]]), receipt(seg=2)]}
    out = mk(events, {'r1': truth_grid(1., .5, .1)})
    res = sc.receipt_nees(out)
    assert res['receipts'][0]['status'] == 'SCORE_ERROR' and res['receipts'][1]['status'] == 'SCORED'
    assert res['summary']['scored_count'] == 1 and res['summary']['skipped_count'] == 1


def test_no_record_and_no_receipts_give_clean_summaries(tmp_path):
    empty = tmp_path/'empty'
    empty.mkdir()
    res = sc.receipt_nees(empty)
    assert res['summary']['status'] == 'NO_STUDENT_RECORD' and res['summary']['receipt_count'] == 0
    out = tmp_path/'none'
    out.mkdir()
    (out/'student_record.json').write_text(json.dumps({'pair': []}))
    res = sc.receipt_nees(out)
    assert res['summary']['status'] == 'OK' and res['summary']['receipt_count'] == 0 and res['receipts'] == []


# --------------------------------------------------------------------------------------------- output file


def test_write_for_run_writes_strict_json_and_never_touches_inputs(tmp_path):
    zero = [[0., 0., 0.], [0., 0., 0.], [0., 0., 0.]]
    out = run_dir(tmp_path, {'r1': [receipt(cov=zero), receipt(seg=2)]}, {'r1': truth_grid(1.02, .5, .1)})
    before = {p: sc.sha256(p) for p in (out/'student_record.json', out/'eval_only/r1/camera_labels.jsonl')}
    short = sc.write_for_run(out)
    assert short == {'schema': sc.SCHEMA, 'path': 'eval_only/dr_receipt_nees.json', 'count': 2, 'scored': 2,
                     'max_nees_xy': pytest.approx(4.), 'max_nees_pose': pytest.approx(4.), 'evaluation_only': True,
                     'receipt_name': 'σ 예산 영수증'}
    def reject(token):
        raise ValueError(token)
    saved = json.loads((out/sc.OUTPUT).read_text(), parse_constant=reject)          # no NaN / Infinity anywhere
    assert saved['schema'] == sc.SCHEMA and saved['summary']['undefined_nees_count'] == 1
    assert {p: sc.sha256(p) for p in before} == before


def test_cli_prints_the_result(tmp_path, capsys):
    out = run_dir(tmp_path, {'r1': [receipt()]}, {'r1': truth_grid(1.02, .5, .1)})
    sc.main([str(out)])
    printed = json.loads(capsys.readouterr().out)
    assert printed['schema'] == sc.SCHEMA and printed['summary']['max_nees_xy_2dof'] == pytest.approx(4.)
    assert not (out/sc.OUTPUT).exists()                                             # printing does not write
    sc.main([str(out), '--write'])
    assert (out/sc.OUTPUT).is_file()


# --------------------------------------------------------------------------------------------- frame convention


def _yaw_of(rotation):
    return math.atan2(rotation[1][0], rotation[0][0])


def _wrap(a):
    return (a + math.pi) % (2*math.pi) - math.pi


def test_frame_convention_against_a_recorded_run():
    """The own report x/y/yaw equals the label base_position_m[:2] / atan2(R10, R00) in the same frame.

    Evidence from the recorded v98 DEV run raise_high_align 1f7fb800 (two own pose means exist in that record, both
    unloaded at t ~ 10 s). A different reference point or axis would show decimetres, not the filter's own sigma."""
    fx = json.loads(FRAME_FIXTURE.read_text())
    assert len(fx['source']['student_record']['sha256']) == 64
    assert set(fx['robots']) == {'r1', 'r2'}
    for rid, r in fx['robots'].items():
        own, truth = r['own_report'], r['truth_nearest']
        x, y, yaw = own['xyyaw']
        tx, ty = truth['base_position_m'][:2]
        gap = abs(truth['t'] - own['t_est'])
        err_xy = math.hypot(tx - x, ty - y)
        err_yaw = _wrap(_yaw_of(truth['base_rotation']) - yaw)
        assert gap < .03, (rid, gap)
        assert err_xy < 1.5*own['std_xy_m'] and err_xy < .03, (rid, err_xy, own['std_xy_m'])
        assert abs(err_yaw) < 2*own['std_yaw_rad'] and abs(err_yaw) < math.radians(1.), (rid, err_yaw)
        # the filter prior of the staged run is the TRUE spawn pose (test setup): same frame, same yaw derivation
        px, py, pyaw = r['staged_prior_mean_xyyaw']
        sx, sy = r['truth_at_spawn']['base_position_m'][:2]
        assert math.hypot(sx - px, sy - py) < 1e-3
        assert abs(_wrap(_yaw_of(r['truth_at_spawn']['base_rotation']) - pyaw)) < 1e-3
    # r2 faces -x: its yaw sits at +-pi, the wrap case the NEES yaw error has to survive
    assert abs(abs(fx['robots']['r2']['own_report']['xyyaw'][2]) - math.pi) < .01


def test_scorer_reproduces_the_recorded_frame_check_through_its_own_code_path(tmp_path):
    """Same two recorded rows pushed through ``receipt_nees`` as if they were receipts (cov = the reported sigma)."""
    fx = json.loads(FRAME_FIXTURE.read_text())
    events, truth = {}, {}
    for rid, r in fx['robots'].items():
        own = r['own_report']
        x, y, yaw = own['xyyaw']
        sxy2, syaw = own['std_xy_m']**2/2, own['std_yaw_rad']
        cov = [[sxy2, 0., 0.], [0., sxy2, 0.], [0., 0., syaw**2]]
        events[rid] = [receipt(rid=rid, t_est=own['t_est'], x=x, y=y, yaw=yaw, cov=cov)]
        t = r['truth_nearest']
        truth[rid] = [(t['t'], *t['base_position_m'][:2], _yaw_of(t['base_rotation']))]
    out = run_dir(tmp_path, events, truth)
    res = sc.receipt_nees(out)
    for row in res['receipts']:
        assert row['status'] == 'SCORED' and abs(row['truth_gap_s']) < .03
        assert row['error_xy_m'] < .03 and abs(row['error_yaw_deg']) < 1.
        assert row['nees_xy_2dof'] < sc.CHI2[2]['p999'] and row['nees_pose_3dof'] < sc.CHI2[3]['p999']


# --------------------------------------------------------------------------------------------- boundary: never to control


def _imports_scorer(tree):
    name = 'eval_highpose_receipt_nees'
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(name in a.name for a in node.names):
            return True
        if isinstance(node, ast.ImportFrom) and (name in (node.module or '') or any(name in a.name for a in node.names)):
            return True
        if isinstance(node, ast.Call):
            fn = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, 'id', '')
            if fn in ('import_module', '__import__') and any(
                    isinstance(a, ast.Constant) and isinstance(a.value, str) and name in a.value for a in node.args):
                return True
    return False


def test_import_scan_detects_every_import_form():
    for src in ('import scripts.eval_highpose_receipt_nees', 'from scripts import eval_highpose_receipt_nees as n',
                'from scripts.eval_highpose_receipt_nees import receipt_nees',
                'import importlib\nimportlib.import_module("scripts.eval_highpose_receipt_nees")',
                '__import__("scripts.eval_highpose_receipt_nees")'):
        assert _imports_scorer(ast.parse(src)), src
    assert not _imports_scorer(ast.parse('"""mentions eval_highpose_receipt_nees"""\nimport math'))


def test_no_control_module_imports_the_scorer():
    scanned = 0
    for folder in ('harness', 'sim'):
        for path in sorted((ROOT/folder).rglob('*.py')):
            scanned += 1
            assert not _imports_scorer(ast.parse(path.read_text(), str(path))), f'{path} imports the evaluation scorer'
    assert scanned > 50
    # the one allowed caller is the runner, after the loop, in the finally block
    runner = (ROOT/'scripts/run_pair_highpose.py').read_text()
    assert runner.count('eval_highpose_receipt_nees') == 1
    tree = ast.parse(runner)
    func = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'student_run_case')
    final = next(n.finalbody for n in ast.walk(func) if isinstance(n, ast.Try) and n.finalbody)
    assert any(_imports_scorer(n) for n in final)


def test_scorer_depends_on_harness_constants_only():
    tree = ast.parse((ROOT/'scripts/eval_highpose_receipt_nees.py').read_text())
    modules = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert {m for m in modules if m.startswith('harness')} == {'harness.zone_pair_highpose_dr_checkpoint'}


# --------------------------------------------------------------------------------------------- runner hook


def _probe_run(tmp_path, monkeypatch, name, *, runtime_cls=None, backend_cls=None):
    from tests.test_zone_final_pair_v3 import FakePhysics
    from tests.test_highpose_dev_pilot import dev_file, admit, _ProbeRuntime
    from harness import zone_pair_highpose_contract as c
    from scripts import run_pair_highpose as run
    path, _ = dev_file(tmp_path)
    sha = c.base.sha(path)
    admit(monkeypatch, sha)
    case = c.cases('p03')[0]
    bundle = {**c.bundle(case['map_id'], 'p03', c.DEV_PILOT), 'case': case, 'source_sha': 'a'*40}
    runtime_cls = runtime_cls or _ProbeRuntime
    return run.student_run_case(bundle, tmp_path/name, seed=911, backend_factory=backend_cls or FakePhysics,
                                runtime_factory=lambda *a, **k: runtime_cls(*a, **k),
                                calibration=path, calibration_sha=sha, probe='raise_high')


def test_runner_hook_writes_the_file_and_leaves_the_status_alone(tmp_path, monkeypatch):
    result = _probe_run(tmp_path, monkeypatch, 'probe')
    assert result['status'] == 'STAGE_PROBE_REACHED' and result['protocol_complete'] is False
    short = result['receipt_nees_eval_only']
    assert short['count'] == 0 and short['max_nees_xy'] is None and short['path'] == sc.OUTPUT
    out = tmp_path/'probe'
    assert json.loads((out/sc.OUTPUT).read_text())['summary']['receipt_count'] == 0
    assert json.loads((out/'result.json').read_text())['receipt_nees_eval_only'] == short
    assert sc.OUTPUT in json.loads((out/'artifacts.sha256.json').read_text())        # hashed with the other artifacts


def test_runner_hook_scores_a_recorded_receipt_after_the_loop(tmp_path, monkeypatch):
    from tests.test_zone_final_pair_v3 import FakePhysics
    from tests.test_highpose_dev_pilot import _ProbeRuntime

    class TruthPhysics(FakePhysics):
        def __init__(self, bundle, out, *, seed):
            super().__init__(bundle, out, seed=seed)
            write_truth(out, 'r1', truth_grid(1.02, .5, .1, 0., 30.))

    class ReceiptRuntime(_ProbeRuntime):
        def record(self):
            return {'pair': [{'robots': {'r1': {'events': [receipt(t_est=7.)]}}}]}

    baseline = _probe_run(tmp_path, monkeypatch, 'a')
    result = _probe_run(tmp_path, monkeypatch, 'b', runtime_cls=ReceiptRuntime, backend_cls=TruthPhysics)
    assert result['status'] == baseline['status'] == 'STAGE_PROBE_REACHED'
    assert result['receipt_nees_eval_only']['count'] == 1
    assert result['receipt_nees_eval_only']['max_nees_xy'] == pytest.approx(4.)
    saved = json.loads((tmp_path/'b'/sc.OUTPUT).read_text())
    assert saved['receipts'][0]['status'] == 'SCORED' and saved['receipts'][0]['truth_gap_s'] == pytest.approx(0, abs=.03)


def test_runner_hook_error_does_not_change_the_run_status(tmp_path, monkeypatch):
    baseline = _probe_run(tmp_path, monkeypatch, 'a')

    def boom(out):
        raise RuntimeError('scorer exploded')
    monkeypatch.setattr(sc, 'write_for_run', boom)
    result = _probe_run(tmp_path, monkeypatch, 'b')
    assert result['status'] == baseline['status'] == 'STAGE_PROBE_REACHED'
    assert result['protocol_complete'] == baseline['protocol_complete']
    assert result['receipt_nees_eval_only'] == {'error': 'RuntimeError: scorer exploded'}
    assert 'record_error' not in result and 'cleanup_error' not in result
    saved = json.loads((tmp_path/'b'/'result.json').read_text())
    assert saved['status'] == baseline['status'] and saved['receipt_nees_eval_only']['error'].startswith('RuntimeError')
    assert not (tmp_path/'b'/sc.OUTPUT).exists()


def test_runner_hook_import_error_does_not_change_the_run_status(tmp_path, monkeypatch):
    import sys
    import scripts
    baseline = _probe_run(tmp_path, monkeypatch, 'a')
    monkeypatch.delattr(scripts, 'eval_highpose_receipt_nees')
    monkeypatch.setitem(sys.modules, 'scripts.eval_highpose_receipt_nees', None)       # the import inside the hook fails
    result = _probe_run(tmp_path, monkeypatch, 'b')
    assert result['status'] == baseline['status'] == 'STAGE_PROBE_REACHED'
    assert result['receipt_nees_eval_only']['error'].startswith('ModuleNotFoundError')


def test_runner_hook_is_skipped_without_a_student_record(tmp_path, monkeypatch):
    from tests.test_highpose_dev_pilot import _ProbeRuntime

    class NoRecord(_ProbeRuntime):
        def record(self):
            raise RuntimeError('record failed')
    result = _probe_run(tmp_path, monkeypatch, 'probe', runtime_cls=NoRecord)
    assert result['status'] == 'HOST_ERROR' and 'record_error' in result            # the run's own failure, unchanged
    assert 'receipt_nees_eval_only' not in result
