"""Design evidence only: saved logs, algebra and synthetic PF; no plant/model.

Write only loaded_stage_metrics.json beside this file. Evaluation files are
opened only after own-input sample selection. No estimates feed a controller.
"""
from __future__ import annotations
import bisect
from collections import Counter, defaultdict
import hashlib
import importlib.abc
import json
import math
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RAW = Path('/Users/changmin/projects/ugrp/outputs')
sys.path.insert(0, str(ROOT))
BLOCKED = {'mujoco', 'torch', 'tensorflow', 'requests', 'httpx'}
class Boundary(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in BLOCKED:
            raise ImportError('design boundary: ' + fullname)
sys.meta_path.insert(0, Boundary())
import numpy as np
from harness.owncam_localizer import OwnCamLocalizer, LoadState

HASHES = {}
def read(p, lines=False):
    p = Path(p)
    b = p.read_bytes()
    HASHES[str(p)] = hashlib.sha256(b).hexdigest()
    return [json.loads(x) for x in b.splitlines() if x] if lines else json.loads(b)
def summary(xs):
    a = np.array(xs, dtype=float)
    return dict(n=len(a), min=float(a.min()), p50=float(np.median(a)),
                p90=float(np.quantile(a, .9)), max=float(a.max())) if len(a) else {'n': 0}
def time(e):
    return float(e.get('sim_s', e.get('sim_time_s', e.get('t', 0.))))
def phase(events, t):
    states = [e for e in events if e['event'] == 'state' and time(e) <= t + 1e-6]
    return states[-1]['state'] if states else 'approach'
def own_point(f, events):
    r = f['report']
    return dict(t=f['t'], frame_id=f['frame_id'], phase=phase(events, f['t']),
                xyyaw=r['xyyaw'], sigma_xy_m=r['std_xy_m'], sigma_yaw_deg=math.degrees(r['std_yaw_rad']),
                tag_age_s=r['since_tag_s'], load_state=r['load_state'], n_eff=r['n_eff'])
def evaluated(p, truth, times, rid):
    # As-of only; never interpolate through a future frame/state.
    j = bisect.bisect_right(times, p['t']) - 1
    assert j >= 0
    g = truth[j]['robots'][rid]
    age = p['t'] - times[j]
    assert age <= .051, age
    err = math.dist(p['xyyaw'][:2], g[:2])
    return {**p, 'eval_match_age_s': age, 'eval_gt_xyyaw': g,
            'eval_xy_error_m': err, 'error_over_sigma_xy': err / p['sigma_xy_m'],
            'eval_yaw_error_deg': abs(math.degrees((p['xyyaw'][2]-g[2]+math.pi)%(2*math.pi)-math.pi))}

def dev_metrics():
    out = []
    for run in read(HERE/'dev-main.json')['runs']:
        root = Path(run['raw_root'])
        bots = read(root/'robots.json'); pairs = read(root/'pair_records.json')
        commands = read(root/'commands.jsonl', True)
        own = {}
        for rid in ('r1', 'r2'):
            events = pairs[0]['robots'].get(rid, {}).get('events', []) if pairs else []
            stops=run['robots'][rid].get('actual_stops', [])
            stop_t=min((e['sim_s'] for e in stops),default=math.inf)
            fs = [f for f in bots[rid]['frames'] if f['report']['initialized'] and f['t'] <= stop_t+1e-6]
            selected = [f for f in fs if phase(events, f['t']) in
                        ('align', 'grasp', 'wait_close', 'wait_lift', 'lift', 'wait_carry', 'carry', 'lower')]
            if not selected:
                continue
            own[rid] = (events, selected, fs[-1], stop_t)
        # Truth is evaluation-only, after sample selection by own state.
        truth = read(root/'eval_only/trace.jsonl', True)
        tt = [e['t'] for e in truth]
        rr = {'id':run['id'], 'source_sha':run['source_sha'], 'raw_root':str(root), 'robots':{}}
        for rid,(events,fs,stop_frame,stop_t) in own.items():
            pts = [evaluated(own_point(f,events),truth,tt,rid) for f in fs]
            align = [p for p in pts if p['phase']=='align']
            metric = {'first':pts[0], 'last':pts[-1], 'frames':len(pts),
                      'stop_t':stop_t,'last_report_at_or_before_abort':evaluated(own_point(stop_frame,events),truth,tt,rid),
                      'error_over_sigma_xy':summary([p['error_over_sigma_xy'] for p in pts]),
                      'error_gt_2sigma_frames':sum(p['error_over_sigma_xy'] > 2 for p in pts),
                      'phase_frames':dict(Counter(p['phase'] for p in pts)),
                      'load_state_frames':dict(Counter(p['load_state'] for p in pts))}
            if align:
                a,b=align[0],align[-1]
                metric['align']={'first':a,'last':b,'duration_s':b['t']-a['t'],
                    'pf_net_translation_m': math.dist(a['xyyaw'][:2],b['xyyaw'][:2]),
                    'eval_net_translation_m': math.dist(a['eval_gt_xyyaw'][:2],b['eval_gt_xyyaw'][:2])}
            ls=LoadState();switches=[];last=False
            for c in commands:
                if c['robot_id'] != rid: continue
                new=ls.command(c)
                if new != last:
                    switches.append({'t':c['t'],'loaded':bool(new),'phase':phase(events,c['t']),
                                     'command':{k:v for k,v in c.items() if k in ('kind','servo_id','pulse')}})
                last=new
            metric['command_load_switches']=switches
            rr['robots'][rid]=metric
        out.append(rr)
    return out

def m2_metrics():
    shadow=read(HERE/'m2-shadow-main.json'); durations=defaultdict(list);rows=[];phases=Counter();gaps=[]
    by_stage=defaultdict(lambda:defaultdict(list)); load_ages=[]
    for run in shadow['runs']:
        root=RAW/run['id'];result=read(root/'result.json')
        events=read(root/'events.jsonl',True);inputs=read(root/'inputs.jsonl',True)
        commands=read(root/'commands.jsonl',True)
        # Verify the inherited replay's source manifests without replaying its JPEGs.
        for name,expected in run['hashes'].items():
            assert HASHES[str(root/name)] == expected, (root,name)
        row={'id':run['id'],'source_sha':run['source_sha'],'development_seed':result.get('development_seed'),
             'stage':result['stage'],'robots':{}}
        for rid in ('r1','r2'):
            es=[e for e in events if e['robot']==rid];states=[e for e in es if e['event']=='state']
            segments=[]
            for a,b in zip(states,states[1:]):
                if a['state'] in ('wait_lift','lift','wait_carry','carry','wait_lower','lower'):
                    dt=time(b)-time(a);durations[a['state']].append(dt)
                    by_stage[result['stage']][a['state']].append(dt)
                    segments.append({'phase':a['state'],'t0':time(a),'t1':time(b),'duration_s':dt})
            reject=run['robots'][rid]['first_shadow_postapproach_gate_reject']
            assert reject is not None
            phases[reject['phase']]+=1;gaps.append(reject['report']['since_tag_s'])
            ls=LoadState();switches=[];last=False
            for c in commands:
                if c['robot']!=rid:continue
                new=ls.command(c)
                if new!=last:switches.append({'t':c['t'],'loaded':bool(new),'phase':phase(es,c['t'])})
                last=new
            prior=[s for s in switches if s['t']<=reject['sim_s'] and s['loaded']]
            loaded_age=reject['sim_s']-prior[-1]['t'] if prior else None
            if loaded_age is not None:load_ages.append(loaded_age)
            loaded_input=[f for f in inputs if f['robot']==rid and f['state'] in
                          ('wait_lift','lift','wait_carry','carry','wait_lower','lower')]
            row['robots'][rid]={'segments':segments,'load_switches':switches,
                'saved_loaded_frame_count':len(loaded_input),'shadow_first_reject':reject,
                'seconds_since_loaded_command_at_shadow_reject':loaded_age,
                'vo_pose_events':sum(e['event']=='vo_pose' and e.get('pose') is not None for e in es)}
        rows.append(row)
    return {'run_count':len(rows),'trace_count':2*len(rows),'first_reject_phase':dict(phases),
            'tag_age_at_reject_s':summary(gaps),'phase_duration_s':{k:summary(v) for k,v in durations.items()},
            'phase_duration_by_stage_s':{s:{k:summary(v) for k,v in d.items()} for s,d in by_stage.items()},
            'seconds_since_loaded_command_at_shadow_reject':summary(load_ages),
            'reject_load_states':dict(Counter(b['shadow_first_reject']['report']['load_state'] for r in rows for b in r['robots'].values())),
            'runs':rows,'scope':'49 success-selected historical runs; 98 inherited conditional PF prefixes, not new rollouts'}

def noise_metrics():
    p=read(ROOT/'experiments/2026-09-26-zone-owncam-loop-v2/calibration_loop_v2.json')['params']
    grid=[]
    for mode in ('motion','motion_loaded'):
        ab=p[mode]['noise_abs'];q=ab[2]**2*.05
        for dt in (.05,.025,.01):
            loc=OwnCamLocalizer({'bounds_m':[-100,100,-100,100],'obstacles':[],
                                'landmarks':{'tags':[]}},p,seed=20260927)
            loc.initialized=True;loc.load.loaded=(mode=='motion_loaded')
            # Identical zero-spread, zero-motion synthetic initial particles, no tags.
            for t in np.arange(dt,10.+dt/2,dt):loc.predict_to(float(t))
            e=loc.estimate()
            grid.append({'mode':mode,'external_predict_interval_s':dt,'elapsed_s':10.,
                         'predicted_yaw_std_deg':math.degrees(ab[2]*math.sqrt(10*dt)),
                         'synthetic_pf_yaw_std_deg':math.degrees(e['std_yaw_rad']),
                         'predicted_xy_std_m':math.hypot(*ab[:2])*math.sqrt(10*dt),
                         'synthetic_pf_xy_std_m':e['std_xy_m']})
    ab=p['motion_loaded']['noise_abs'][2];q=ab*ab*.05
    budgets=[{'initial_yaw_deg':a,'stationary_seconds_to_3deg':
              (math.radians(3)**2-math.radians(a)**2)/q} for a in (0,1,2,2.5)]
    return {'params':p,'variance_rule':'Var(delta_pose)=noise_velocity^2 * sum(dt_k^2), not Q * sum(dt_k)',
            'zero_motion':grid,'loaded_yaw_variance_rate_rad2_per_s_at_50ms':q,
            'stationary_budget':budgets,'loaded_to_unloaded_yaw_variance_ratio':
            (ab/p['motion']['noise_abs'][2])**2,
            'door_axial_segments':[{'length_m':d,'nominal_s_at_m2_speed':d/(.06*.772)} for d in (.55,.65,.85,.8)],
            'scope':'analytic and pure PF synthetic sensitivity; not fitted replacement noise, no physical claim'}

def main():
    out={'schema':'ugrp.loaded_stage_design_metrics.v1','physics_steps':0,'model_calls':0,
         'eval_used_for_control':False,'dev':dev_metrics(),'m2':m2_metrics(),'noise':noise_metrics()}
    assert not (BLOCKED & set(sys.modules))
    out['blocked_modules_not_imported']=True
    out['source_hashes']=HASHES
    out['analysis_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (HERE/'loaded_stage_metrics.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'dev_runs':len(out['dev']),'m2_runs':out['m2']['run_count'],
        'rejects':out['m2']['first_reject_phase'],'source_files_hashed':len(HASHES),
        'noise_grid':out['noise']['zero_motion'],'budgets':out['noise']['stationary_budget']},indent=2))
if __name__=='__main__':main()
