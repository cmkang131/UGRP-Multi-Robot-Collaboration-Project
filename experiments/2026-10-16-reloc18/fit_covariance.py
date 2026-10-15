"""GCP2 offline calibration from complete, untrimmed reloc17 R2 distributions."""
import hashlib,json,math,platform,subprocess
from pathlib import Path
import numpy as np
from scipy.stats import norm,chi2
RUNS=Path('/home/ugrp/ugrp-sim/runs')
def load(p):return p.read_text() if p.exists() else subprocess.check_output(['zstd','-dc',str(p)+'.zst'],text=True)
def rows(p):return [json.loads(s) for s in load(p).splitlines()]
def wrap(x):return math.atan2(math.sin(x),math.cos(x))
def main():
    assert platform.node().startswith('ugrp-sim-gcp2')
    from harness.natural_floor_slam import compose
    residuals=[];rates=[];sources=[];diagnostics=[];correlation=[]
    for seed in (93584,93583):
        raw=RUNS/f'reloc17-r2-selfmap-{seed}-47670d14/raw'
        trace=rows(raw/'trace.jsonl');truth={round(x['t'],6):x for x in rows(raw/'eval_only/trajectory.jsonl')}
        first=truth[round(trace[0]['t'],6)];origin=np.array([*first['robot_xyz_m'][:2],first['robot_yaw_rad']]);a=origin[2]
        R=np.array([[math.cos(a),math.sin(a),0],[-math.sin(a),math.cos(a),0],[0,0,1]])
        commands=[];measurements=[];measurement_times=[]
        for t in trace:
            gt=truth.get(round(t['t'],6))
            if gt is None:continue
            actual=np.array([*gt['robot_xyz_m'][:2],gt['robot_yaw_rad']]);reg=t.get('static_registration',{})
            packet=reg.get('reloc12',{}).get('replay',{});odom=packet.get('own_odometry_pose')
            if odom is not None:
                pred=compose(origin,odom);e=pred-actual;e[2]=wrap(e[2]);local=R@e;elapsed=t['t']-trace[0]['t']
                if elapsed>0:rates.append(abs(local)/math.sqrt(elapsed))
                commands.append(dict(t=t['t'],elapsed=elapsed,error_xy_m=float(np.linalg.norm(e[:2])),error_yaw_deg=abs(math.degrees(e[2]))))
            if reg.get('updated') and reg.get('world_pose') is not None:
                e=np.asarray(reg['world_pose'])-actual;e[2]=wrap(e[2]);residuals.append(e);measurements.append(e.tolist());measurement_times.append(t['t'])
        # Initial-positive-sequence integrated autocorrelation time in SIM
        # seconds. This diagnoses repeated PF posterior reuse; no truth-based
        # candidate pruning, no hand-selected frame spacing.
        m=np.asarray(measurements)
        for axis in range(3):
            v=m[:,axis]-m[:,axis].mean();den=float(v@v)
            ac=[]
            if den>0:
                for lag in range(1,len(v)):
                    rho=float(v[:-lag]@v[lag:]/den)
                    if rho<=0:break
                    ac.append(rho)
            dt=float(np.median(np.diff(measurement_times)))
            correlation.append(dict(seed=seed,axis=axis,positive_lags=len(ac),integrated_sim_s=dt*(1+2*sum(ac))))
        sources.extend(dict(path=str(p if p.exists() else Path(str(p)+'.zst')),sha256=hashlib.sha256((p if p.exists() else Path(str(p)+'.zst')).read_bytes()).hexdigest()) for p in (raw/'trace.jsonl',raw/'eval_only/trajectory.jsonl'))
        diagnostics.append(dict(seed=seed,command_drift_bins=[dict(sim_interval=[lo,hi],N=len(v),xy_p50_m=float(np.median([x['error_xy_m'] for x in v])) if v else None,xy_p95_m=float(np.percentile([x['error_xy_m'] for x in v],95)) if v else None) for lo,hi in ((0,20),(20,40),(40,60)) for v in [[x for x in commands if lo<=x['elapsed']<hi]]],measurement_N=len(measurements)))
    z=float(norm.ppf(.975));residuals=np.asarray(residuals);rates=np.asarray(rates)
    config=dict(schema='ugrp.reloc18.covariance.v1',method='diagonal zero-centered 95-percentile envelope / normal central-95 quantile; no oracle outlier pruning',
        fit_scope='both already-seen DEV seeds, all delivered fresh static PF poses; exploratory calibration, not held-out validation',
        measurement_N=len(residuals),measurement_abs_p95=np.percentile(abs(residuals),95,axis=0).tolist(),
        measurement_covariance_world=np.diag((np.percentile(abs(residuals),95,axis=0)/z)**2).tolist(),
        command_rate_N=len(rates),command_covariance_per_sim_s=np.diag((np.percentile(rates,95,axis=0)/z)**2).tolist(),
        alpha=.01,dof=3,chi2_threshold=float(chi2.ppf(.99,3)),normal_central95=z,
        measurement_correlation_sim_s=max(x['integrated_sim_s'] for x in correlation),correlation_diagnostics=correlation,
        sources=sources,diagnostics=diagnostics,
        limitations='successive PF posteriors and RGB frames correlated; chi-square false-reject interpretation assumes independent Gaussian prediction/measurement and is only nominal here; fixed covariance envelope does not certify non-Gaussian tails or all seeds')
    out=RUNS/'reloc18-audit/covariance-fit.json';out.write_text(json.dumps(config,indent=2)+'\n');print(json.dumps(config,indent=2))
if __name__=='__main__':main()
