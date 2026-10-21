"""pairact-r1 dry-run (SYNTHETIC_DRYRUN): synth -> convert -> stage sidecar, labels, determinism,
P5 config keys and plumbing report. No training, no model forward, no simulator."""
import ast
import json
from pathlib import Path
import subprocess

import pytest

from scripts import pairact_r1_dryrun_check as chk
from scripts import pairact_r1_dryrun_synth as syn

ROOT = Path(__file__).resolve().parents[1]
TEACHER_C5 = '75929e7719ad98a089e3dda5251f4249d8bae511'
ROOT_C5 = 'a93082c343ef5f3687851bf4b0c9fb0f2484ada1'


@pytest.fixture(scope='module')
def pipeline(tmp_path_factory):
    from harness.grasp_act_data import convert
    from scripts.build_pairact_r1_stage_targets import build
    base = tmp_path_factory.mktemp('dryrun')
    manifest = syn.generate(base / 'in')
    protocol = json.loads((base / 'in/protocol.json').read_text())
    report = convert(base / 'in', protocol, base / 'ds')
    sidecar = build(base / 'ds', base / 'st')
    return base, manifest, report, sidecar


def test_convert_and_sidecar_cover_all_stages(pipeline):
    base, manifest, report, sidecar = pipeline
    assert report['status'] == 'complete' and report['complete'] is True
    assert sorted((e['split'], e['robot_id']) for e in report['episodes']) == [
        ('train', 'r1'), ('train', 'r2'), ('validation', 'r1'), ('validation', 'r2')]
    assert all(e['missing_done_skills'] == [] for e in report['episodes'])
    assert sidecar['missing_stages'] == []
    assert set(sidecar['h0_stage_counts']) == set(syn.p.STAGES)
    assert manifest['stages_covered'] == sorted(syn.p.STAGES)
    v = chk.verify_data(base / 'ds', base / 'st/stage-targets.json')
    assert v['passed'] and v['label'] == syn.LABEL and v['synthetic'] is True


def test_labels_everywhere(pipeline):
    base, manifest, report, _ = pipeline
    assert report['protocol']['label'] == syn.LABEL and report['protocol']['synthetic'] is True
    assert manifest['label'] == syn.LABEL and manifest['synthetic'] is True
    for seed in (syn.TRAIN_SEED, syn.VALIDATION_SEED):
        run = base / 'in' / f'seed-{seed}'
        assert 'SYNTHETIC' in (run / 'SOURCE_SHA').read_text()
        for name in ('SYNTHETIC.json', 'raw/plan.json', 'raw/result.json', 'raw/student-camera.json'):
            data = json.loads((run / name).read_text())
            assert data['label'] == syn.LABEL and data['synthetic'] is True, name
        teacher = [json.loads(s) for s in (run / 'raw/teacher-r1.jsonl').read_text().splitlines()]
        assert all(r['synthetic'] is True for r in teacher)
    assert 'SYNTHETIC_DRYRUN' in syn.LABEL and '판정 아님' in syn.LABEL and 'teacher 시연 아님' in syn.LABEL


def test_deterministic(tmp_path):
    a = syn.generate(tmp_path / 'a')
    b = syn.generate(tmp_path / 'b')
    assert a['files'] == b['files'] and len(a['files']) > 200
    with pytest.raises(FileExistsError):
        syn.generate(tmp_path / 'a')


def test_synthetic_seeds_do_not_overlap_registered_ranges(tmp_path):
    spec = json.loads(syn.SEEDS_JSON.read_text())
    assert syn.seed_overlap([syn.TRAIN_SEED, syn.VALIDATION_SEED], spec) == []
    heldout = spec['splits']['heldout']['first']
    assert syn.seed_overlap([heldout], spec)[0]['range'] == 'splits.heldout'
    with pytest.raises(ValueError, match='overlap'):
        syn.generate(tmp_path / 'x', validation_seed=heldout)
    # v3-shard seeds.json adds train_extension / pilot top-level ranges; they are scanned too.
    spec2 = {**spec, 'pilot': {'first': 9990002, 'last': 9990002}}
    assert syn.seed_overlap([syn.VALIDATION_SEED], spec2)[0]['range'] == 'pilot'
    # P5 dry-run world seed (P2 smoke-1c world 1): outside train/validation/heldout.
    hits = syn.seed_overlap([8420001], spec)
    assert hits and all(h['range'].startswith('known_ranges:') for h in hits)


def _git_show(rev, path):
    r = subprocess.run(['git', '-C', str(ROOT), 'show', f'{rev}:{path}'], capture_output=True, text=True)
    if r.returncode:
        pytest.fail(f'{rev}:{path} not in local repo (git fetch origin first)')
    return r.stdout


def _assigned(source, name):
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Assign) and any(getattr(t, 'id', None) == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise KeyError(name)


def test_student_eval_config_keys_match_teacher_and_root_c5(tmp_path):
    teacher = _git_show(TEACHER_C5, 'harness/pairact_student_eval.py')
    root = _git_show(ROOT_C5, 'scripts/run_warp_flow_teacher.py')
    assert set(_assigned(teacher, 'CONFIG_KEYS')) == chk.STUDENT_EVAL_KEYS
    assert _assigned(teacher, 'MODE') == chk.STUDENT_EVAL_MODE
    assert set(_assigned(root, 'STUDENT_EVAL_KEYS')) == chk.STUDENT_EVAL_KEYS
    assert _assigned(root, 'STUDENT_SHA') == chk.STUDENT_SHA
    out = tmp_path / 'student-eval.json'
    rc = chk.main(['student-eval-config', '--python', '/v/bin/python', '--source', '/s/student',
                   '--model', '/r/smoke/step-000300/actor', '--config', '/s/student/cfg.json',
                   '--out', str(out), '--skip-source-head-check'])
    assert rc == 0
    assert set(json.loads(out.read_text())) == chk.STUDENT_EVAL_KEYS
    label = json.loads((tmp_path / 'student-eval.LABEL.json').read_text())
    assert label['label'] == syn.LABEL and '판정 아님' in label['label_p5'] and '합성' in label['label_p5']
    with pytest.raises(ValueError, match='absolute'):
        chk.student_eval_config(python='rel', source='/s', model='/m', config='/c')


def test_worker_tree_files_identical_to_pinned_student_sha():
    # The checkpoint records sha256 of these files; the P5 worker (pinned STUDENT_SHA) re-checks them.
    files = ['harness/pairact_r1.py', 'harness/pairact_r1_student.py', 'scripts/pairact_r1_student_worker.py',
             'harness/beamact3.py', 'harness/grasp_act_contract.py', 'harness/grasp_act_policy.py',
             'harness/grasp_act_data.py', 'scripts/train_grasp_act.py',
             'experiments/2026-10-21-pairact-r1/PAIRACT_R1_TRAIN_CONFIG_DRAFT.json']
    r = subprocess.run(['git', '-C', str(ROOT), 'diff', '--quiet', chk.STUDENT_SHA, '--', *files])
    assert r.returncode == 0


def _p5_tree(tmp_path, *, teacher_steps=0, gt=0, funnel=True):
    raw = tmp_path / 'p5/world-000/raw'
    raw.mkdir(parents=True)
    se = {'teacher_steps': teacher_steps, 'gt_inputs_to_student': gt}
    if funnel:
        se['funnel'] = {'order': [], 'reached': {'approach': False}, 'first_failure': 'approach'}
    (raw / 'result.json').write_text(json.dumps({'student_execution': True, 'student_eval': se}))
    summary = {'status': 'complete', 'HOST_ERROR': 0, 'student_eval': {'mode': chk.STUDENT_EVAL_MODE},
               'worlds': [{'world': 0, 'seed': 8420001, 'success': False, 'teacher_steps': teacher_steps,
                           'raw': str(raw)}]}
    (tmp_path / 'p5/summary.json').write_text(json.dumps(summary))
    return tmp_path / 'p5'


def test_p5_report_plumbing_only(tmp_path):
    good = chk.p5_report(_p5_tree(tmp_path / 'a'))
    assert good['passed'] and good['label_p5'] == chk.P5_LABEL and good['judgement'] is None
    assert good['worlds'][0]['success_not_a_judgement'] is False
    assert not chk.p5_report(_p5_tree(tmp_path / 'b', teacher_steps=1))['passed']
    assert not chk.p5_report(_p5_tree(tmp_path / 'c', gt=2))['passed']
    assert not chk.p5_report(_p5_tree(tmp_path / 'd', funnel=False))['passed']


def test_compare_outputs_is_exact():
    torch = pytest.importorskip('torch')
    x = {'action_chunk': torch.zeros(1, 8, 14), 'stage_logits': torch.ones(1, 8, 8)}
    same = chk.compare_outputs(x, {k: v.clone() for k, v in x.items()})
    assert all(v['torch_equal'] for v in same.values())
    y = {**x, 'stage_logits': x['stage_logits'] + 1e-6}
    assert not chk.compare_outputs(x, y)['stage_logits']['torch_equal']
