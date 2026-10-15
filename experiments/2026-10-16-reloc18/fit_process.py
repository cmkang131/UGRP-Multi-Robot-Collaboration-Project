"""Offline transition-residual Q fit, not cumulative global-error-as-process-noise."""
import hashlib,inspect,json,math,platform,subprocess
from pathlib import Path
import numpy as np
from scipy.stats import norm
from harness.natural_floor_slam import compose,wrap
from harness.selfmap4_geometry import inverse
from sim.solo_carry_pose import CommandPose
RUNS=Path('/home/ugrp/ugrp-sim/runs')
def text(p):return p.read_text() if p.exists() else subprocess.check_output(['zstd','-dc',str(p)+'.zst'],text=True)
def rows(p):return [json.loads(s) for s in text(p).splitlines()]
def mode(delta):
    return 'moving' if np.any(np.asarray(delta)!=0) else 'idle'
def fit(records):
    result={};z=float(norm.ppf(.975))
    for kind in ('idle','moving'):
        selected=[x for x in records if x['mode']==kind]
        if not selected:raise RuntimeError('missing command noise condition '+kind)
        e=np.asarray([x['error'] for x in selected]);dt=float(np.median([x['dt'] for x in selected]));taus=[]
        # Native-step residual sequence, zero outside this command class. Keep
        # original temporal spacing when estimating positive-sequence ACF.
        full=np.array([x['error'] if x['mode']==kind else [0,0,0] for x in records])
        for axis in range(3):
            v=full[:,axis]-full[:,axis].mean();den=float(v@v);positive=[]
            if den>0:
                for lag in range(1,len(v)):
                    rho=float(v[:-lag]@v[lag:]/den)
                    if rho<=0:break
                    positive.append(rho)
            taus.append(1+2*sum(positive))
        p95=np.percentile(abs(e),95,axis=0);diag=(p95/z)**2/dt*np.asarray(taus)
        result[kind]=dict(N=len(selected),native_sim_step_s=dt,absolute_transition_residual_p95=p95.tolist(),
            empirical_mean_residual=e.mean(0).tolist(),integrated_correlation_steps=taus,covariance_per_sim_s=np.diag(diag).tolist())
    return result
def main():
    assert platform.node().startswith('ugrp-sim-gcp2')
    corpora={'carry':[],'selfmap':[]};sources=[]
    for seed in (93266,93315):
        raw=RUNS/f'reloc17-r2-carry-{seed}-47670d14/raw';p=json.loads(text(raw/'plan.json'));c=rows(raw/'teacher-commands.jsonl');ev={round(e['t'],5):e for e in rows(raw/'eval-only.jsonl') if 'base_xyz' in e}
        flags={k:v for k,v in p.items() if k in inspect.signature(CommandPose).parameters and k not in ('start','now','tracking_static')}
        for k in list(flags):
            if any(s in k for s in ('tracking','heading','compass','active_view')):flags[k]=False
        cp=CommandPose(p['task_start'],now=c[0]['t'],**flags)
        for a,b in zip(c,c[1:]):
            dt=b['t']-a['t'];cp.issue(a['command'],dt);da=np.asarray(cp.last_delta)
            g0,g1=ev[round(a['t'],5)],ev[round(b['t'],5)]
            actual=compose(inverse([*g0['base_xyz'][:2],g0['base_yaw_rad']]),[*g1['base_xyz'][:2],g1['base_yaw_rad']]);error=actual-da;error[2]=wrap(error[2])
            corpora['carry'].append(dict(mode=mode(da),dt=dt,error=error.tolist()))
        sources.extend(raw/x for x in ('teacher-commands.jsonl','eval-only.jsonl'))
    for seed in (93584,93583):
        raw=RUNS/f'reloc17-r2-selfmap-{seed}-47670d14/raw';tr=rows(raw/'trace.jsonl');ev={round(e['t'],6):e for e in rows(raw/'eval_only/trajectory.jsonl')}
        for a,b in zip(tr,tr[1:]):
            a0=a['static_registration']['reloc12']['replay']['own_odometry_pose'];b0=b['static_registration']['reloc12']['replay']['own_odometry_pose']
            da=compose(inverse(a0),b0);g0,g1=ev[round(a['t'],6)],ev[round(b['t'],6)]
            actual=compose(inverse([*g0['robot_xyz_m'][:2],g0['robot_yaw_rad']]),[*g1['robot_xyz_m'][:2],g1['robot_yaw_rad']]);error=actual-da;error[2]=wrap(error[2])
            corpora['selfmap'].append(dict(mode='idle' if np.array_equal(a0,b0) else 'moving',dt=b['t']-a['t'],error=error.tolist()))
        sources.extend(raw/x for x in ('trace.jsonl','eval_only/trajectory.jsonl'))
    d=dict(schema='ugrp.reloc18.process_cov.v1',method='native transition residual in robot body frame; abs p95/1.96, divided by native SIM step; initial-positive-sequence ACF inflation; no initial world-pose error included',
        scope='same already-seen DEV calibration, no held-out covariance certification; bias and non-Gaussian tails remain limitations',
        fits={k:fit(v) for k,v in corpora.items()},sources=[dict(path=str(p if p.exists() else Path(str(p)+'.zst')),sha256=hashlib.sha256((p if p.exists() else Path(str(p)+'.zst')).read_bytes()).hexdigest()) for p in sources])
    p=RUNS/'reloc18-audit/process-covariance.json';p.write_text(json.dumps(d,indent=2)+'\n');print(json.dumps(d['fits'],indent=2))
if __name__=='__main__':main()
