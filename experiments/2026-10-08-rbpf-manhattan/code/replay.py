"""egomap24 scorer/replayer reused with only yaw option and new output roots."""
import argparse
import importlib.util
import json
import math
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[3]
EXP=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from harness.rbpf_rejection import install as selective, OPTION as SELECTIVE
from harness.rbpf_manhattan import install as yaw_install, OPTION
from harness.self_map_prob import wrap
spec=importlib.util.spec_from_file_location('egomap24',ROOT/'experiments/2026-10-07-rbpf-rejection/code/replay.py')
previous=importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
previous.OUT=Path('/Users/changmin/projects/ugrp/outputs/rbpf-manhattan-v1')
previous.EXP=EXP
OUT,RAW=previous.OUT,previous.RAW
load,dump,sha,rows=previous.load,previous.dump,previous.sha,previous.rows
BASE=Path('/Users/changmin/projects/ugrp/outputs/rbpf-rejection-v1/on')


def verify_off():
    receipt=load(BASE/'seal.json')
    assert sha(BASE/'prediction.json')==receipt['sha256']
    # Full serialized prediction (poses including covariances, grid, decisions,
    # ledger), not a hand-selected subset, must remain byte-identical.
    identical=(OUT/'off/prediction.json').read_bytes()==(BASE/'prediction.json').read_bytes()
    dump(OUT/'off/byte-verification.json',dict(equal=identical,sha256=sha(OUT/'off/prediction.json'),baseline_sha256=receipt['sha256']))
    assert identical,'YAW_OFF_BYTES_CHANGED'
    print('off complete prediction bytes identical',flush=True)


previous.verify_off=verify_off


def predict(mode):
    # Private replay module injection, no process-wide estimator monkeypatch.
    previous.install=lambda grid,**unused:yaw_install(selective(grid,rbpf_rejection=SELECTIVE),yaw_prior=OPTION if mode=='on' else 'off')
    previous.predict(mode)


def score():
    import contextlib, io
    with contextlib.redirect_stdout(io.StringIO()):
        previous.score()  # same sealed-prediction boundary and original map metrics
    result=load(EXP/'results/comparison.json')
    truth={round(r['t'],6):r for r in rows(RAW/'eval_only/trajectory.jsonl')}
    start=truth[min(truth)]
    curves={}
    for mode in ('off','on'):
        pred=load(OUT/mode/'prediction.json')
        poses=pred['poses']
        actual=np.array([truth[round(r['t'],6)]['robot_yaw_rad'] for r in poses])
        error=wrap(np.array([r['pose'][2] for r in poses])+start['robot_yaw_rad']-actual)
        mod90=(error+math.pi/4)%(math.pi/2)-math.pi/4
        degrees=np.degrees(error)
        sigma_xy=np.array([np.sqrt(np.linalg.eigvalsh(np.array(r['covariance'])[:2,:2]).max()) for r in poses])
        r=result['modes'][mode]
        r['yaw']=dict(end_signed_deg=float(degrees[-1]),rmse_deg=float(np.sqrt(np.mean(degrees**2))),
            abs_median_deg=float(np.median(abs(degrees))),abs_p95_deg=float(np.quantile(abs(degrees),.95)),
            mod90_rmse_deg=float(np.sqrt(np.mean(np.degrees(mod90)**2))),
            mod90_end_signed_deg=float(np.degrees(mod90[-1])),n=len(poses))
        r['sensor_updates']=sum(d.get('sensor_weight_update',False) for d in pred['decisions'])
        r['manhattan']=pred['grid'].get('manhattan')
        curves[mode]=dict(t_s=[r['t']-start['t'] for r in poses],yaw_error_deg=degrees.tolist(),
                          yaw_mod90_error_deg=np.degrees(mod90).tolist(),sigma_xy_m=sigma_xy.tolist())
    off,on=result['modes']['off'],result['modes']['on']
    result['gate']=dict(within_2sigma=on['error_2sigma_ratio']<=1.,
        region_precision_improves=on['observed_region']['precision'] is not None and off['observed_region']['precision'] is not None
                                  and on['observed_region']['precision']>off['observed_region']['precision'])
    result.pop('physical_admitted')
    result['next_physical_proposal_allowed']=all(result['gate'].values())
    result['physical_runs']=0
    result['qualification']='Same input frontend; selective on in both; change yaw_prior only. Acquisition/B/contact metrics are historical, not a new control run.'
    dump(EXP/'results/comparison.json',result)
    dump(OUT/'evaluation-curves.json',curves)
    plot(curves)
    print(json.dumps({k:result[k] for k in ('gate','next_physical_proposal_allowed')},indent=2))
    for mode,r in result['modes'].items():
        print(mode,json.dumps({k:r[k] for k in ('endpoint_error_m','sigma_xy_m','error_sigma_ratio','yaw','observed_region','manhattan')},indent=2))


def plot(curves):
    sys.path.insert(0,str(ROOT/'outputs/self-map-plot-deps'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,1,figsize=(9,6),sharex=True)
    for mode,c in curves.items():
        axes[0].plot(c['t_s'],c['yaw_error_deg'],label=mode)
        axes[1].plot(c['t_s'],c['yaw_mod90_error_deg'],label=mode)
    axes[0].set(ylabel='Yaw error (deg)',title='Same 891 timestamps; selective resampling on in both')
    axes[1].set(xlabel='Time from recorded start (s)',ylabel='Yaw error mod 90 (deg)',ylim=(-45,45))
    for ax in axes:
        ax.axhline(0,color='.5',linestyle='--');ax.legend()
    fig.tight_layout()
    (EXP/'figures').mkdir(exist_ok=True)
    fig.savefig(EXP/'figures/yaw.png',dpi=130)
    plt.close(fig)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=['off','on','score'])
    a=parser.parse_args()
    score() if a.mode=='score' else predict(a.mode)
