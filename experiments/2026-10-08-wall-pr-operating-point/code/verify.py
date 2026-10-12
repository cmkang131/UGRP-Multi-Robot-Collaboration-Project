"""Audit sealed predictions/selection without another held evaluation."""
from run import *
from harness.self_wall_pr import fingerprint

spec=frozen();development=load(EXP/'results/development.json');held_result=load(EXP/'results/held.json')
assert held_result['selection_freeze_sha256']==sha(EXP/'freeze.json')
subprocess.run(['git','merge-base','--is-ancestor',held_result['source_sha'],head()],cwd=ROOT,check=True)
assert subprocess.check_output(['git','show',held_result['source_sha']+':'+str((EXP/'freeze.json').relative_to(ROOT))],cwd=ROOT)==(EXP/'freeze.json').read_bytes()
assert not held_result['export_start']
records={}
for seed in EPISODES:
    folder=verify_prediction(seed);seal=load(folder/'seal.json');ep=EPISODES[seed]
    expected=load(ep/'artifacts.sha256.json')
    gt_hashes={name:sha(ep/name) for name in ('eval_only/trajectory.jsonl','eval_only/camera.jsonl','inputs/static_map.json')}
    assert all(h==expected[name] for name,h in gt_hashes.items())
    grid=load(folder/'grid.json');segments=load(folder/'segments.json');support=load(folder/'support.json')
    assert (folder/'grid.json').read_bytes()==(ep/'grid.json').read_bytes()
    representations={}
    for kind,base in (('grid',grid),('segments',segments)):
        assert apply(base) is base
        original=fingerprint(base)
        assert spec['selected'][kind]==select(development['representations'][kind]['candidates'])
        assert len(development['representations'][kind]['candidates'])==40
        point=spec['selected'][kind]['operating_point']
        selected=apply(base,support[kind],wall_validation=OPTION,**point)
        assert fingerprint(base)==original
        if seed=='32002':
            assert selected==load(folder/f'{kind}-selected.json')
            assert load(folder/'applied-operating-points.json')[kind]==point
        if kind=='grid':
            assert [c for c in base['cells'] if c[2]<=0]==[c for c in selected['cells'] if c[2]<=0]
            original_cells={tuple(c[:2]):c for c in base['cells']}
            assert all(c==original_cells[tuple(c[:2])] for c in selected['cells'])
            assert {k:v for k,v in base.items() if k!='cells'}=={k:v for k,v in selected.items() if k not in ('cells','wall_validation')}
        else:
            assert all(line in base['segments'] for line in selected['segments'])
        representations[kind]=dict(off_identity=True,input_unchanged=True,geometry_unchanged=True,
            fixed_point=point,free_cells_unchanged=True if kind=='grid' else None)
    decisions=load(ep/'decisions.json')
    counts=dict(Counter(d['reason'] for d in decisions))
    records[seed]=dict(seal_sha256=sha(folder/'seal.json'),prediction_source_sha=seal['source_sha'],
        off_grid_file_bytes_identical=True,rgb=seal['rgb_frames'],inserted=seal['ledger_frames'],
        actual_contact_columns=seal['actual_contact_columns'],decision_reason_counts=counts,
        decisions_sha256=sha(ep/'decisions.json'),gt_evaluation_only_hashes=gt_hashes,representations=representations)
user_files={'analyze_wall_detection.py':'26c818f1cd4673c7f4a1b6ab535b4e70ac68167f1f56989f10c8c6bebe0c3dd0',
 'create_wall_visualizations.py':'e2b77c1f678d1ba27658dffecf99bcf7bfd7c12c056d41869a7a38cc482f8efa',
 'create_wall_visualizations_v2.py':'8e6fa7f6598336bc6f7c61ad956d1902be9925443d7656cea2801362195d83c8',
 'parameter_probe.py':'43f91584406ba91a73032514b8409357fc9c7ac2c3cbc3e72d26bce5257e103b'}
for name,h in user_files.items():assert sha(ROOT/name)==h,name
assert '12 passed' in (RAW/'tests.log').read_text()
manifest={str(p.relative_to(RAW)):dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(RAW.rglob('*')) if p.is_file()}
dump(EXP/'results/raw-manifest.json',dict(root=str(RAW),files=manifest))
dump(EXP/'results/verification.json',dict(records=records,preregistration_commit='e48ece04',
    prediction_code_commit='0f0e5830',operating_point_commit=held_result['source_sha'],
    held_evaluations=1,held_threshold_sweeps=0,post_result_threshold_changes=0,
    previously_seen_held_recording=True,tests=12,physics=0,render=0,models=0,lock_acquired=False,
    original_untracked_hashes=user_files,raw_manifest_sha256=sha(EXP/'results/raw-manifest.json'),
    result_hashes={n:sha(EXP/'results'/n) for n in ('development.json','held.json','raster-diagnostic.json')},
    figures={p.name:dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted((EXP/'figures').iterdir())},
    raw_path=str(RAW),export_start=False))
assert 'mujoco' not in sys.modules
print('PASS: frozen points, raw/input/code hashes, off bytes, free values, line geometry, user files, 12 tests')
