"""Artifact audit only: do not rescore or rerun the held detector."""
from common import *
from compare import frozen

spec=frozen();records={}
for seed,ep in EPISODES.items():
    raw=RAW/seed;off=load(raw/'off/seal.json');seal=load(raw/'comparison/seal.json')
    for where,manifest in [(raw/'off',off),(raw/'comparison',seal)]:
        for n,h in manifest['files'].items():assert sha(where/n)==h
        for n,h in manifest['input_hashes'].items():assert sha(ep/n)==h
    for n,h in off['rgb_hashes'].items():assert sha(ep/n)==h
    for n,h in seal['code_hashes'].items():assert sha(ROOT/n)==h
    assert (raw/'comparison/historical-grid.json').read_bytes()==(ep/'grid.json').read_bytes()
    original=load(ep/'graph.json')['ledger']
    for cond in ('off','on'):
        ledger=load(raw/f'comparison/{cond}-ledger.json')
        assert [(r['t'],r['frame_id'],r['pose'],r['camera']) for r in ledger]==[(r['t'],r['frame_id'],r['pose'],r['camera']) for r in original]
    diag=load(EXP/f'results/{seed}-diagnosis.json');assert sha(raw/'diagnosis.json')==diag['sha256']
    for summary in diag['summary'].values():assert sum(x['count'] for x in summary['categories'].values())==summary['false_points']
    result=load(EXP/f'results/{seed}-comparison.json')
    assert result['source_seal_sha256']==sha(raw/'comparison/seal.json')
    assert result['conditions']['off']['points']['precision']==diag['summary']['all']['precision']
    assert len(rows(raw/'off/points.jsonl'))==len(rows(raw/'comparison/on-points.jsonl'))==891
    for option in ('off','on'):
        metrics=result['conditions'][option]
        assert metrics['inserted_nonempty_frames']==len(original)
        assert metrics['points']['correct']<=metrics['points']['points']
    reasons=dict(Counter(r['reason'] for r in load(ep/'decisions.json')))
    expected=load(ep/'artifacts.sha256.json')
    for n in ('eval_only/trajectory.jsonl','eval_only/camera.jsonl','eval_only/setup.json','scene.xml','inputs/static_map.json'):
        assert sha(ep/n)==expected[n]
    records[seed]=dict(input_rgb_frames=len(off['rgb_hashes']),detector_frames=891,inserted_frames=len(original),
        own_pose_and_camera_exact=True,off_observation_exact_frames=len(original),historical_grid_bytes_identical=True,
        decision_reasons=reasons,baseline_sha=off['source_sha'],prediction_sha=seal['source_sha'],
        ground_truth_only_during_evaluation=True,source_hashes={n:sha(ep/n) for n in expected if n in ('scene.xml','eval_only/trajectory.jsonl','eval_only/camera.jsonl','decisions.json')},
        point_gate=result['detector_gate'],on_map_gates=result['conditions']['on']['map_gates'])
    if seed=='32002':
        freeze_sha=result['source_sha']
        assert subprocess.check_output(['git','show',freeze_sha+':'+str((EXP/'freeze.json').relative_to(ROOT))],cwd=ROOT)==(EXP/'freeze.json').read_bytes()
previous=load(ROOT/'experiments/2026-10-08-wall-pr-operating-point/results/verification.json')
for n,h in previous['original_untracked_hashes'].items():assert sha(ROOT/n)==h
assert '16 passed' in (RAW/'tests.log').read_text()
fixtures=ROOT/'tests/fixtures/wall_contact_types'
assert sha(fixtures/'dev326.jpg')==load(fixtures/'frame.json')['sha256']
for p in (EXP/'figures').iterdir():assert p.stat().st_size<=1024*1024
assert sum(p.stat().st_size for p in EXP.rglob('*') if p.is_file() and '__pycache__' not in p.parts)<5*1024*1024
manifest={str(p.relative_to(RAW)):dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(RAW.rglob('*')) if p.is_file()}
dump(EXP/'results/raw-manifest.json',dict(root=str(RAW),files=manifest))
dump(EXP/'results/verification.json',dict(records=records,preregistration='56860d86',method_commit='26a007d7',freeze_commit=freeze_sha,
    tests=16,physics=0,render=0,models=0,lock_acquired=False,held_on_evaluations=1,retuning=0,
    original_untracked_unchanged=True,raw_path=str(RAW),manifest_sha256=sha(EXP/'results/raw-manifest.json'),
    figure_hashes={p.name:dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted((EXP/'figures').iterdir())},
    fixture_hashes={p.name:sha(p) for p in sorted(fixtures.iterdir()) if p.is_file()},
    note='Default off golden bytes unchanged; paired evaluator recomputes both weights from saved post-scan covariance; historical grid kept separately.'))
assert 'mujoco' not in sys.modules
print('PASS: sealed inputs, frozen option, held once, 111 off observations, history bytes, poses, 16 tests, artifacts')
