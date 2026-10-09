"""Post-seal bidirectional means/scatter and preregistered gain-only eligibility."""
import hashlib
import json
import sys
from pathlib import Path
import numpy as np
from scipy.stats import t as student_t

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from harness.self_pulse_odom import model, MODEL_SHA256
EXP=Path(__file__).resolve().parents[1]
RAW=Path('/Users/changmin/projects/ugrp/outputs/pulse-rotation-audit-v1/measurement')


def load(p):return json.loads(p.read_text())
def rows(p):return [json.loads(s) for s in p.read_text().splitlines()]
def dump(p,d):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(d,indent=2,ensure_ascii=False,allow_nan=False)+'\n')


def fit(records):
    output={}
    for sign in (-1,1):
        group=[r for r in records if r['sign']==sign]
        train=[r for r in group if r['split']=='fit']
        check=[r for r in group if r['split']=='check']
        x=np.array([r['predicted_deg']/r['pulses'] for r in train])
        y=np.array([r['actual_deg']/r['pulses'] for r in train])
        gain=float(x@y/(x@x))
        # Repeated modes in the same repetition are a cluster, not independent n=6.
        rep=np.array([np.mean([r['actual_deg']/r['predicted_deg'] for r in train if r['repeat']==i]) for i in (1,2,3)])
        half=float(student_t.ppf(.975,2)*rep.std(ddof=1)/np.sqrt(3))
        modes={m:float(np.mean([r['actual_deg']/r['predicted_deg'] for r in train if r['mode']==m]))
               for m in ('single','continuous')}
        off=np.array([(r['actual_deg']-r['predicted_deg'])/r['pulses'] for r in check])
        on=np.array([(r['actual_deg']-gain*r['predicted_deg'])/r['pulses'] for r in check])
        output[str(sign)]=dict(gain=gain,ci95=[gain-half,gain+half],train_n=len(train),check_n=len(check),
            independent_repeat_n=3,mode_gains=modes,relative_mode_gap=abs(modes['single']-modes['continuous'])/gain,
            check_rmse_deg_per_pulse_off=float(np.sqrt(np.mean(off**2))),
            check_rmse_deg_per_pulse_on=float(np.sqrt(np.mean(on**2))),
            systematic_error_deg_per_pulse=float(np.mean(y-x)),
            residual_std_deg_per_pulse=float(np.std(y-gain*x,ddof=1)))
    gates={}
    for sign,r in output.items():
        gates[sign]=dict(under_gain_ci_lower_gt1=r['ci95'][0]>1,
                         single_continuous_agree=r['relative_mode_gap']<=.05,
                         check_rmse_improves=r['check_rmse_deg_per_pulse_on']<r['check_rmse_deg_per_pulse_off'])
    return dict(directions=output,gates=gates,eligible=all(all(g.values()) for g in gates.values()))


def main():
    for p,h in load(RAW/'artifacts.sha256.json').items():
        assert hashlib.sha256((RAW/p).read_bytes()).hexdigest()==h,p
    result=load(RAW/'result.json')
    assert result['status']=='RECORDED'
    gt=rows(RAW/'eval_only/trajectory.jsonl')
    wheels=rows(RAW/'eval_only/wheels.jsonl')
    ts=np.array([r['t'] for r in gt])
    yaw=np.unwrap([r['robot_yaw_rad'] for r in gt])
    xy=np.array([r['robot_xyz_m'][:2] for r in gt])
    records=[]
    for b in load(RAW/'schedule.json')['blocks']:
        start=result['start_sim_s']+b['start_tick']/20
        end=result['start_sim_s']+b['end_tick']/20
        profile=model()['profiles'][f"0:turn:{b['sign']*.35:.2f}:0.10"]
        actual=float(np.degrees(np.interp(end,ts,yaw)-np.interp(start,ts,yaw)))
        pred=float(np.degrees(profile['mean_delta'][2])*b['pulses'])
        j=int(np.argmin(abs(ts-end)))
        records.append(dict(**b,start_s=start,end_s=end,actual_deg=actual,predicted_deg=pred,
            error_deg=actual-pred,gain=actual/pred,
            tail_after_horizon_deg=float(np.degrees(np.interp(end+1.,ts,yaw)-np.interp(end,ts,yaw))),
            drift_xy_m=float(np.linalg.norm(xy[j]-xy[np.argmin(abs(ts-start))])),
            wheel_speed_at_horizon_rad_s=wheels[j]['qvel_rad_s']))
    summary=[]
    for sign in (-1,1):
        for mode in ('single','continuous'):
            group=[r for r in records if r['sign']==sign and r['mode']==mode]
            per=np.array([r['actual_deg']/r['pulses'] for r in group])
            summary.append(dict(sign=sign,mode=mode,n=len(group),predicted_deg_per_pulse=group[0]['predicted_deg']/group[0]['pulses'],
                actual_mean_deg_per_pulse=float(per.mean()),actual_std_deg_per_pulse=float(per.std(ddof=1)),
                mean_gain=float(np.mean([r['gain'] for r in group])),
                mean_tail_after_horizon_deg=float(np.mean([r['tail_after_horizon_deg'] for r in group]))))
    report=dict(source=result['source_sha'],base_model_sha256=MODEL_SHA256,method='bilateral rotation-only UMBmark-inspired diagnostic; not full square UMBmark',
                physical=result,summary=summary,fit=fit(records),records=records)
    dump(EXP/'results/measurement.json',report)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(9,3.7))
    for ax,sign in zip(axes,(-1,1)):
        for mode,color in [('single','tab:blue'),('continuous','tab:orange')]:
            group=[r for r in records if r['sign']==sign and r['mode']==mode]
            ax.plot([r['repeat'] for r in group],[r['gain'] for r in group],'o-',label=mode,color=color)
        ax.axhline(1,color='gray',linestyle='--')
        ax.axvline(3.5,color='gray',linestyle=':')
        ax.set(title='CW (-)' if sign<0 else 'CCW (+)',xlabel='repeat (1-3 fit / 4-5 check)',ylabel='actual / v122 yaw')
        ax.legend()
    fig.tight_layout()
    (EXP/'figures').mkdir(exist_ok=True)
    fig.savefig(EXP/'figures/rotation-gain.png',dpi=150)
    print(json.dumps(dict(summary=summary,fit=report['fit']),indent=2))


if __name__=='__main__':main()
