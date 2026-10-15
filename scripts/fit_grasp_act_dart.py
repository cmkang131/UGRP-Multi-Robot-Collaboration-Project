"""Fit diagonal DART covariance from complete saved heldout first-action errors."""
import argparse
import json
from pathlib import Path
from harness.grasp_act_data import read_rows, sha256, write_json
from harness.grasp_act_dart import fit_diagonal


def fit(timesteps,manifest,output):
    data=json.loads(Path(manifest).read_text());rows=read_rows(timesteps)
    expected={str(e['seed']):e['rows_selected'] for e in data['episodes'] if e['split']=='validation'}
    from collections import Counter
    counts=Counter(r['sample_id'].split(':')[0].removeprefix('train-') for r in rows)
    if dict(counts)!=expected:raise ValueError('full heldout episode/row coverage required')
    model=fit_diagonal(rows)
    model.update(source_timesteps_sha256=sha256(timesteps),dataset_manifest_sha256=sha256(manifest),
                 calibration_seeds=list(map(int,expected)),
                 calibration_holdout_is_now_development=True)
    write_json(output,model)
    return model


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('timesteps','manifest','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();fit(a.timesteps,a.manifest,a.output)


if __name__=='__main__':main()
