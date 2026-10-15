"""Offline command shadow / full-pose recovery / heading residual evaluation."""
import collections,hashlib,inspect,json,math,platform,subprocess
from pathlib import Path
import numpy as np
from scipy.stats import norm
from sim.solo_carry_pose import CommandPose
from harness.natural_floor_slam import wrap
RUNS=Path('/home/ugrp/ugrp-sim/runs')
def load(p):return p.read_text() if p.exists() else subprocess.check_output(['zstd','-dc',str(p)+'.zst'],text=True)
def obj(p):return json.loads(load(p))
def rows(p):return [json.loads(s) for s in load(p).splitlines()]
def dist(x):return dict(N=len(x),p50=float(np.percentile(x,50)),p95=float(np.percentile(x,95)),end=float(x[-1])) if x else dict(N=0)
def main():
    assert platform.node().startswith('ugrp-sim-gcp2')
    reports=[];rates=[];head_errors=[];pose_errors=[];tracker_errors=[];sources=[]
    for seed in (93266,93315):
        raw=RUNS/f'reloc17-r2-carry-{seed}-47670d14/raw';p=obj(raw/'plan.json');d=obj(raw/'result.json');c=rows(raw/'teacher-commands.jsonl');ev=rows(raw/'eval-only.jsonl');by={round(e['t'],5):e for e in ev}
        flags={k:v for k,v in p.items() if k in inspect.signature(CommandPose).parameters and k not in ('start','now','tracking_static')}
        for k in list(flags):
            if any(s in k for s in ('tracking','heading','compass','active_view')):flags[k]=False
        cp=CommandPose(p['task_start'],now=c[0]['t'],**flags);scored=[];heading={};trackers={}
        for i,x in enumerate(c):
            e=by[round(x['t'],5)];actual=np.array([*e['base_xyz'][:2],e['base_yaw_rad']]);error=np.asarray(cp.pose)-actual;error[2]=wrap(error[2]);elapsed=x['t']-c[0]['t']
            if elapsed>0:rates.append(abs(error)/math.sqrt(elapsed))
            scored.append(dict(elapsed=elapsed,phase=x['phase'],command_xy=float(np.linalg.norm(error[:2])),command_yaw=abs(math.degrees(error[2])),visual_xy=e['map_pose_error_xy_m'],visual_yaw=abs(math.degrees(e['map_pose_error_yaw_rad']))))
            h=x.get('map_pose',{}).get('reloc15_heading',{})
            if h.get('observed_yaw_rad') is not None and h.get('exposure_sim_t') is not None:heading[round(h['exposure_sim_t'],5)]=h
            tracker=x.get('map_pose',{}).get('reloc14_tracking',{})
            key=tracker.get('sensor_updates')
            if tracker.get('updated') and key not in trackers:
                trackers[key]=tracker
                er=np.asarray(tracker['pose'])-actual;er[2]=wrap(er[2]);tracker_errors.append(er)
            if i+1<len(c):cp.issue(x['command'],c[i+1]['t']-x['t'])
        for t,h in heading.items():
            e=by.get(t)
            if e is not None:head_errors.append(wrap(h['observed_yaw_rad']-e['base_yaw_rad']))
        localizer=d['lookaround']['localizer'].get('localizer',{})
        for v in localizer.get('views',[]):
            e=by.get(round(v['t'],5));candidate=v.get('fix_acceptance',{}).get('view_statistics',{}).get('candidate_pose',v.get('posterior'))
            if e is not None and candidate is not None:
                err=np.asarray(candidate)-np.array([*e['base_xyz'][:2],e['base_yaw_rad']]);err[2]=wrap(err[2]);pose_errors.append(err)
        sources.extend(dict(path=str(f if f.exists() else Path(str(f)+'.zst')),sha256=hashlib.sha256((f if f.exists() else Path(str(f)+'.zst')).read_bytes()).hexdigest()) for f in (raw/'teacher-commands.jsonl',raw/'eval-only.jsonl',raw/'result.json'))
        reports.append(dict(seed=seed,scope='command-only integration on original visual-controlled trajectory; evaluation only',
            errors={k:dist([s[k] for s in scored]) for k in ('command_xy','command_yaw','visual_xy','visual_yaw')},
            bins=[dict(sim_interval=[lo,hi],errors={k:dist([s[k] for s in scored if lo<=s['elapsed']<hi]) for k in ('command_xy','command_yaw','visual_xy','visual_yaw')}) for lo,hi in ((0,50),(50,100),(100,150))],
            heading_N=len(heading),tracker_N=len(trackers),relook_keys=list(localizer),relook_views_N=len(localizer.get('views',[]))))
    z=float(norm.ppf(.975));rates=np.asarray(rates);pose_errors=np.asarray(pose_errors);tracker_errors=np.asarray(tracker_errors)
    config=dict(schema='ugrp.reloc18.carry_covariance.v1',fit_scope='original two reloc17 R2 carry DEV trajectories; no truth-based pruning',
        command_covariance_per_sim_s=np.diag((np.percentile(rates,95,axis=0)/z)**2).tolist(),command_N=len(rates),
        heading_N=len(head_errors),heading_abs_p95_rad=float(np.percentile(abs(np.asarray(head_errors)),95)),heading_variance=float((np.percentile(abs(np.asarray(head_errors)),95)/z)**2),
        full_pose_N=len(pose_errors),full_pose_covariance_world=np.diag((np.percentile(abs(pose_errors),95,axis=0)/z)**2).tolist() if len(pose_errors) else None,
        tracker_N=len(tracker_errors),tracker_abs_p95=np.percentile(abs(tracker_errors),95,axis=0).tolist(),
        tracker_covariance_world=np.diag((np.percentile(abs(tracker_errors),50,axis=0)/norm.ppf(.75))**2).tolist(),
        tracker_abs_p50=np.percentile(abs(tracker_errors),50,axis=0).tolist(),
        tracker_method='robust zero-centered absolute residual median / normal central50 quantile; all 69 raw candidates, no truth pruning; AMCL hit-core plus outlier-mixture motivation; p95 heavy tails recorded separately, not Gaussian variance inflation',
        sources=sources,reports=reports)
    out=RUNS/'reloc18-audit/carry-fit.json';out.write_text(json.dumps(config,indent=2)+'\n');print(json.dumps(config,indent=2))
if __name__=='__main__':main()
