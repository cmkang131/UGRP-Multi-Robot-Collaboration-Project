"""Final artifact verification; no detector rerun or repeated held scoring."""
from common import *
from compare import frozen

frozen();records={}
for seed,ep in EPISODES.items():
    folder=RAW/seed/'comparison-complete';seal=load(folder/'seal.json')
    for n,h in seal['files'].items():assert sha(folder/n)==h,n
    for n,h in seal['code_hashes'].items():assert sha(ROOT/n)==h,n
    for n,h in seal['input_hashes'].items():assert sha(ep/n)==h,n
    assert sha(OLD_RAW/seed/'off/points.jsonl')==seal['off_points_sha256']
    result=load(EXP/f'results/{seed}-comparison.json')
    assert result['source_seal_sha256']==sha(folder/'seal.json')
    assert (folder/'historical-grid.json').read_bytes()==(ep/'grid.json').read_bytes()
    original=load(ep/'graph.json')['ledger']
    for condition in ('off','on'):
        ll=load(folder/f'{condition}-ledger.json')
        assert [(r['frame_id'],r['t'],r['pose'],r['camera']) for r in ll]==[(r['frame_id'],r['t'],r['pose'],r['camera']) for r in original]
        v=result['conditions'][condition]
        assert 0<=v['points']['recalled_contacts']<=v['points']['visible_contacts']
        if condition=='off':
            for kind in ('grid','segments'):
                assert (folder/f'off-{kind}.json').read_bytes()==(OLD_RAW/seed/f'comparison/off-{kind}.json').read_bytes()
    assert result['conditions']['off']['points']['visible_contacts']==result['conditions']['on']['points']['visible_contacts']
    assert len(rows(folder/'on-points.jsonl'))==891
    if seed=='31001':
        assert (RAW/seed/'comparison/on-points.jsonl').read_bytes()==(folder/'on-points.jsonl').read_bytes()
    if seed=='32002':
        freeze_commit=result['source_sha']
        assert subprocess.check_output(['git','show',freeze_commit+':'+str((EXP/'freeze.json').relative_to(ROOT))],cwd=ROOT)==(EXP/'freeze.json').read_bytes()
    reasons=Counter(r['reason'] for r in load(ep/'decisions.json'))
    audit=load(EXP/f'results/{seed}-retention.json')
    assert sum(v['on'] for v in audit['false_categories'].values())+len(audit['extra_false_points'])==result['conditions']['on']['points']['points']-result['conditions']['on']['points']['correct']
    records[seed]=dict(prediction_sha=seal['source_sha'],input_frames=891,
        insertion_times=len(original),nonempty_insertions_on=result['conditions']['on']['inserted_nonempty_frames'],
        original_reasons=dict(reasons),original_pose_and_camera_exact=True,
        original_grid_bytes_identical=True,paired_off_maps_identical_to_egomap37=True,
        point_recall_same_denominator=True,point_gate=result['detector_gate'],
        map_gates=result['conditions']['on']['map_gates'],selected_gates=result['conditions']['on']['selected_gates'])
previous=load(ROOT/'experiments/2026-10-08-wall-pr-operating-point/results/verification.json')
for n,h in previous['original_untracked_hashes'].items():assert sha(ROOT/n)==h
for p in (EXP/'figures').iterdir():assert p.stat().st_size<=1024*1024
assert sum(p.stat().st_size for p in EXP.rglob('*') if p.is_file() and '__pycache__' not in p.parts)<5*1024*1024
assert '12 passed' in (RAW/'tests.log').read_text()
manifest={str(p.relative_to(RAW)):dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(RAW.rglob('*')) if p.is_file()}
dump(EXP/'results/raw-manifest.json',dict(root=str(RAW),files=manifest))
dump(EXP/'results/verification.json',dict(records=records,tests=12,preregistration='ce4f920b',implementation='0a77c5c1',
    empty_scan_adapter_fix='565bf428',freeze_commit=freeze_commit,held_on_evaluations=1,
    physics=0,render=0,models=0,lock_acquired=False,retuning=0,original_untracked_unchanged=True,
    raw_path=str(RAW),manifest_sha256=sha(EXP/'results/raw-manifest.json'),
    figure_hashes={p.name:dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted((EXP/'figures').iterdir())}))
assert 'mujoco' not in sys.modules
print('PASS: frozen option, held once, identical off maps/history/poses, RGB hashes, 12 tests, artifact sizes')
