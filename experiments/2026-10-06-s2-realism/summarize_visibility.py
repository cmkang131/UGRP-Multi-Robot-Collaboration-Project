"""Posthoc visibility replay score; evaluation truth is confined to this file."""
import json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
import replay_visibility as replay
import summarize_soft_mcl as score
old=replay.old
for key in ('max_update_gap_sim_s','min_independent_updates','independent_spacing_sim_s'):
    assert replay.CRITERIA[key]==score.m.CRITERIA[key]


def summarize(out):
    dest=out/'summary.json'
    if dest.exists():raise FileExistsError(dest)
    baseline=old.RAW/'s2-soft-mcl-20261007/summary.json'
    prior=json.loads(baseline.read_text());rows=list(prior['rows']);hashes={str(baseline):old.digest(baseline)}
    for seed,sha in old.RUNS.items():
        path=out/f's{seed}-{replay.OPTION}.json';r=json.loads(path.read_text())
        assert r['gt_inputs'] is False and r['commands_fixed'] is True
        assert r['criteria_sha256']==old.digest(old.HERE/'visibility-criteria.json')
        assert r['soft_measurement']['parameters']==replay.PARAMS
        assert r['approximation']==old.approximation(replay.CRITERIA['camera_variant'])
        raw=Path(r['source_raw'])
        for rel,digest in r['source_hashes'].items():assert old.digest(raw/rel)==digest
        truth_path=raw/'eval_only/trajectory.jsonl'
        truth=[json.loads(l) for l in truth_path.read_text().splitlines()]
        times=np.array([g['t'] for g in truth]);xy=np.array([g['robot_xyz_m'][:2] for g in truth])
        window=r['carry_window'];carry=[p for p in r['rows'] if window[0]<=p['t']<window[1]]
        errors=[float(np.linalg.norm(np.array([p['x'],p['y']])-
            [np.interp(p['t_est'],times,xy[:,i]) for i in (0,1)])) for p in carry]
        updates=score.update_metrics([p['t'] for p in r['soft_measurement']['rows'] if p['visual_weight_update']],window)
        accuracy=score.accuracy(errors);comp=[x for x in rows if x['seed']==seed]
        assert len(comp)==3
        ap=all(accuracy['rmse_m']<b['accuracy']['rmse_m'] for b in comp)
        ap &= all(accuracy['p90_m']<=b['accuracy']['p90_m'] for b in comp if b['variant']!='amcl_likelihood_field_v1')
        masks=[p for p in r['visibility_mask']['rows'] if window[0]<=p['t']<window[1]]
        mask_summary=dict(attempts=len(masks),no_six_visible_columns=sum(p['kept']<6 for p in masks),
            total_detected_columns=sum(p['detected'] for p in masks),total_kept_columns=sum(p['kept'] for p in masks),
            detected_self_shadow=sum(p['detected_self_shadow'] for p in masks),
            detected_cargo_shadow=sum(p['detected_cargo_shadow'] for p in masks))
        rows.append(dict(seed=seed,variant=replay.OPTION,carry_window=window,**updates,accuracy=accuracy,
            accuracy_pass=bool(ap),admission_pass=bool(ap and updates['frequency_pass']),visibility=mask_summary,
            measurement_receipt='soft weight update on visible columns; not absolute fix'))
        hashes[str(path)]=old.digest(path);hashes[str(truth_path)]=old.digest(truth_path)
    geo=out/'geometry-shadow.json';g=json.loads(geo.read_text());hashes[str(geo)]=old.digest(geo)
    features=out/'feature-geometry.json';hashes[str(features)]=old.digest(features)
    result=dict(features=json.loads(features.read_text()),schema='ugrp.s2.visibility.summary.v1',criteria_commit='e2a4558c',candidate_commit='79cfd27d',
        criteria=replay.CRITERIA,rows=rows,geometry={k:v for k,v in g.items() if k!='rows'},
        full_dev_permitted=all(r['admission_pass'] for r in rows if r['variant']==replay.OPTION),
        physics_runs=0,model_calls=0,new_seed=None,source_hashes=hashes,
        source_code_hashes={name:old.digest(old.ROOT/name) for name in (
            'harness/zone_solo_cyan_visibility.py','harness/zone_solo_cyan_likelihood_field.py',
            'experiments/2026-10-06-s2-realism/replay_visibility.py',
            'experiments/2026-10-06-s2-realism/analyze_visibility.py',
            'experiments/2026-10-06-s2-realism/summarize_visibility.py',
            'experiments/2026-10-06-s2-realism/feature_visibility.py')},
        scope='saved commands only; GT posthoc evaluation, not a live mission or admission of unmeasured loaded calibration')
    dest.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(rows=rows,full_dev_permitted=result['full_dev_permitted']),indent=2))


if __name__=='__main__':summarize(Path(sys.argv[1]))
