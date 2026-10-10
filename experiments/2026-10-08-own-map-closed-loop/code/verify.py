"""Post-run evidence audit; no physics/model/replay and no threshold selection."""
from replay import *
from collections import Counter


def main():
    before=load(ROOT/'experiments/2026-10-08-own-map-causal-landmarks/results/utility-on.json')
    after_summary=load(EXP/'results/utility-tempered.json')
    for a,b in zip(before['trials'],after_summary['trials']):
        assert all(a[k]==b[k] for k in ('condition','trial','seed','input_frames','point_samples','landmark_samples','measured_landmarks'))
    prepared=load(CACHE/'prepared.json')
    for p,digest in after_summary['sealed_predictions'].items():assert sha(Path(p))==digest
    for c in ('own','static'):
        for i in range(3):
            p=load(RAW/f'{c}-tempered-{i}.json')
            assert p['prepared_sha256']==sha(CACHE/'prepared.json') and not p['gt_inputs']
            assert p['source_sha'].startswith('56ad5051')
            assert all(r['t']>prepared['cuts'][i]['cut_t']+1e-8 for r in p['rows'])
            assert sha(CACHE/f'maps/{c}-{i}.json')==prepared['cuts'][i]['maps'][c]
    physical=RAW.parent/'new-seed';result=load(physical/'result.json')
    assert result['status']=='RECORDED' and result['source_sha'].startswith('e068a70f')
    for name,digest in load(physical/'artifacts.sha256.json').items():assert sha(physical/name)==digest,name
    snap=load(physical/'snapshot.json');cut=snap['loss_t'];inputs=load(physical/'own-inputs.json')
    assert snap['t']<cut-1e-8 and all(r['t']<cut-1e-8 for r in snap['ledger'])
    assert all(e['source']['t']<cut-1e-8 for e in snap['landmarks']['edges']+snap['landmarks']['doors'])
    assert all(r['t']>cut+1e-8 for r in inputs if r['stage']!='explore')
    assert snap['goal']['t_sim']<cut and not any(abs(r['t']-cut)<1e-8 for r in inputs)
    final_grid=load(physical/'frontend-grid.json')
    # Occupancy is fixed; the old frontend still predicted command odometry
    # between its last insertion (87.9) and loss (91.3). Those diagnostics differ.
    assert all(snap['grid'][k]==final_grid[k] for k in ('robot_id','resolution_m','cells'))
    assert snap['ledger']==load(physical/'frontend-ledger.json')
    cmds=rows(physical/'robots/r3/commands.jsonl')
    assert not any('freeze' in str(r).lower() for r in cmds)
    frames=rows(physical/'robots/r3/frames.jsonl')
    goal_frame=next(r for r in frames if r['frame_id']==int(snap['goal']['obs_id'].rsplit('-',1)[-1]))
    assert sha(physical/goal_frame['path'])==snap['goal']['frame_sha256']
    movie=load(EXP/'results/video.json');assert sha(Path(movie['path']))==movie['sha256']
    assert movie['frames']==len(frames) and movie['fps']==20 and movie['decode_verified']
    managed=load(RAW.parent/'managed-run/manifest.json')
    assert managed['status']=='process_completed' and managed['exit_code']==0
    record=dict(source_sha=head(),prediction_source='56ad5051',physical_source=result['source_sha'],
        offline_trials=6,unique_recordings=1,overlapping_pairs=3,physical_attempts=1,
        causal_prefix_suffix=True,off_prechange_golden=True,parameters_retuned=False,
        snapshot_scans=len(snap['ledger']),snapshot_floor_edges=len(snap['landmarks']['edges']),snapshot_doors=len(snap['landmarks']['doors']),
        declared_goal_source=snap['goal']['obs_id'],video_checked=True,model_calls=0,
        raw_bytes=sum(p.stat().st_size for p in physical.rglob('*') if p.is_file()),
        hashes={str(p):sha(p) for p in [physical/'artifacts.sha256.json',physical/'snapshot.json',physical/'source-admission.json',physical/'lock.json',RAW.parent/'managed-run/manifest.json']})
    dump(EXP/'results/verification.json',record)
    files=[p for p in RAW.parent.rglob('*') if p.is_file()]
    dump(EXP/'results/raw-manifest.json',{str(p):dict(sha256=sha(p),bytes=p.stat().st_size) for p in files})
    print(json.dumps(record,indent=2))


if __name__=='__main__':main()
