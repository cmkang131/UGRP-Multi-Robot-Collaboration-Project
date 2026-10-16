"""Post-score diagnostic only; never fed back to inference."""
import json
import math
import sys
from pathlib import Path
import numpy as np
from replay import RAW, OUT, ROOT, EXP, load, rows, dump, sha
from harness.self_odom_grid import transform
from harness.self_map_prob import wrap
from harness.self_pulse_odom import PulseOdometry


def main():
    prediction = load(OUT/'on/prediction.json')
    assert sha(OUT/'on/prediction.json') == load(OUT/'on/seal.json')['sha256']
    poses = prediction['poses']
    # Command-only mean computed before loading evaluation truth.
    commands = sorted(rows(RAW/'robots/r3/commands.jsonl'), key=lambda r:r['t'])
    driver = PulseOdometry(commands[0]['t'])
    for command in commands:
        if command['t'] < poses[-1]['t']-1e-8:
            driver.command(command)
    driver.advance(poses[-1]['t'])
    truth = {round(r['t'],6):r for r in rows(RAW/'eval_only/trajectory.jsonl')}
    first = truth[min(truth)]
    origin = np.array([*first['robot_xyz_m'][:2], first['robot_yaw_rad']])
    records = []
    for d in prediction['decisions']:
        if not d.get('matching_attempted'):
            continue
        actual = truth[round(d['t'],6)]
        xy = transform([d['pose'][:2]], origin)[0]
        particles = d['particle_events']
        from collections import Counter
        records.append(dict(t=d['t'], reason=d['reason'], resampled=d['resampled'], neff=d['neff'],
            endpoint_error_m=float(np.linalg.norm(xy-np.array(actual['robot_xyz_m'][:2]))),
            signed_yaw_error_deg=math.degrees(float(wrap(d['pose'][2]+origin[2]-actual['robot_yaw_rad']))),
            sigma_xy_m=float(np.sqrt(np.linalg.eigvalsh(np.array(d['covariance'])[:2,:2]).max())),
            particle_reasons=dict(Counter(p['reason'] for p in particles))))
    final = truth[round(poses[-1]['t'],6)]
    dr_error = float(np.linalg.norm(transform([driver.pose[:2]],origin)[0]-np.array(final['robot_xyz_m'][:2])))
    report = dict(command_only_endpoint_error_m=dr_error,
                  command_only_signed_yaw_error_deg=math.degrees(float(wrap(driver.pose[2]+origin[2]-final['robot_yaw_rad']))),
                  accepted=[r for r in records if r['reason']=='improved_proposal'],
                  rejected_tail=records[-5:], matches=records,
                  qualification='evaluation only; no noise/threshold fitting; finite search radius unchanged')
    dump(EXP/'results/diagnosis.json', report)
    sys.path.insert(0,str(ROOT/'outputs/self-map-plot-deps'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,1,figsize=(9,6),sharex=True)
    for ax,mode in zip(axes,('off','on')):
        p=load(OUT/mode/'prediction.json')['poses']
        t=np.array([r['t'] for r in p])-first['t']
        xy=transform([r['pose'][:2] for r in p],origin)
        actual=np.array([truth[round(r['t'],6)]['robot_xyz_m'][:2] for r in p])
        e=np.linalg.norm(xy-actual,axis=1)
        sigma=np.array([np.sqrt(np.linalg.eigvalsh(np.array(r['covariance'])[:2,:2]).max()) for r in p])
        ax.plot(t,e,label='XY error (evaluation only)',color='tab:red')
        ax.plot(t,2*sigma,label='2 x sigma XY',color='tab:blue')
        ax.set(ylabel='m',title=mode+' / same 891 timestamps')
        ax.legend(fontsize=8)
    axes[-1].set_xlabel('Recorded time from start (s)')
    fig.tight_layout()
    (EXP/'figures').mkdir(exist_ok=True)
    fig.savefig(EXP/'figures/uncertainty.png',dpi=130)
    plt.close(fig)
    print(json.dumps({k:v for k,v in report.items() if k not in ('matches','rejected_tail')},indent=2))


if __name__=='__main__': main()
