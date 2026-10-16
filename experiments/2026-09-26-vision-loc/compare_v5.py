#!/usr/bin/env python3
"""Finite VIS5 dev extraction/fit/shadow comparison; no rendering or physics.

--extract reads vision caches and own inputs ONLY. --compare separately reads
evaluation truth for fitting and scoring. Every artifact is exclusive-create.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
from pathlib import Path
from types import SimpleNamespace

import numpy as np

import calibrate_sigma_v4 as cs
import diagnose_v4 as d
import route_audit_v5 as route
import vision_loc as vl
import vision_loc_io as vio
import vision_report_v5 as head

HERE = Path(__file__).resolve().parent
PLAN = HERE/'dev_plan_v5.json'
OUT = HERE.parents[1]/'outputs/vision-loc-v5'
SOURCE_NAMES = ('compare_v5.py','vision_report_v5.py','route_audit_v5.py','vision_pf_v5.py','vision_loc.py',
                'vision_loc_io.py','vision_loc_cli_v5.py','vision_sigma.py','vision_motion.py','calibrate_sigma_v4.py',
                'diagnose_v4.py','dev_plan_v5.json','selected_config_v3.json','calibration_train.json',
                'episodes.json','episodes_v3.json','maps/zone_wide_door_walls_v3_notags.json',
                '../2026-09-26-markerless-probe/markerless_probe.py',
                '../../harness/wall_tags.py','../../sim/masterpi_camera_profile.py')


def save(path, obj):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as f:
        json.dump(obj, f, indent=2, allow_nan=False); f.write('\n')


def jsonl(path, rows):
    with Path(path).open('x') as f:
        for row in rows:
            f.write(json.dumps(row, allow_nan=False)+'\n')


def plan_load(path=PLAN):
    p = vio.load_json(path)
    fit,val = p['fit_episodes'],p['validation_episodes']
    if len(set(fit+val)) != len(fit+val) or not fit or not val:
        raise ValueError('duplicate/overlapping/empty cohorts')
    d.require_dev(fit+val)
    return p


def source_hashes():
    return {str((HERE/name).resolve()):vio.sha_file(HERE/name) for name in SOURCE_NAMES}


def inventory(plan):
    paths = []
    for ep in plan['fit_episodes']+plan['validation_episodes']:
        paths += [vio.RENDER_ROOT/ep/'inputs'/n for n in ('frames.jsonl','commands.jsonl')]
        paths += [vio.PRIMARY_OUT/'r3/dev-grid/a1_open'/f'{ep}.{suffix}'
                  for suffix in ('estimates.jsonl','meta.json')]
        paths += [vio.PRIMARY_OUT/'r3/obs-w6'/f'{ep}.obs.npz']
    paths += [cs.VISW/'robots/r2/inputs'/n for n in ('frames.jsonl','commands.jsonl')]
    return {str(p):vio.sha_file(p) for p in paths}


def verify(hashes):
    return [p for p,h in hashes.items() if vio.sha_file(Path(p)) != h]


def extract(output):
    plan = plan_load(); output.mkdir(parents=True, exist_ok=False)
    sources, inputs = source_hashes(),inventory(plan)
    save(output/'source_freeze.json', {'sources':sources,'inputs':inputs,'plan_sha256':vio.sha_file(PLAN),
         'base_sha':plan['base_sha'],'uncommitted_user_request':True,'python':platform.python_version(),
         'numpy':np.__version__,'load_average_start':os.getloadavg(),'new_model_inference':0,'physics_steps':0})
    cfg,cal = vio.load_json(HERE/'selected_config_v3.json'),vio.load_json(HERE/'calibration_train.json')
    geometry = vl.mp.MapGeometry(vio.load_map(),include_posts=False)
    sequences = []
    for ep in plan['fit_episodes']+plan['validation_episodes']:
        print('EXTRACT',ep,flush=True)
        directory = vio.RENDER_ROOT/ep
        frames = vl.read_jsonl(directory/'inputs/frames.jsonl')
        commands = vl.read_jsonl(directory/'inputs/commands.jsonl')
        own = cs.command_features(frames,commands,cfg['measurement']['settle_s'])
        rows = vl.read_jsonl(vio.PRIMARY_OUT/'r3/dev-grid/a1_open'/f'{ep}.estimates.jsonl')
        meta = vio.load_json(vio.PRIMARY_OUT/'r3/dev-grid/a1_open'/f'{ep}.meta.json')
        if meta['failure'] is not None or meta['frames_written'] != len(frames) or meta['frames'] != len(frames):
            raise ValueError('incomplete baseline')
        if meta['config']['value'] != cfg or meta['checkpoint_sha256'] != plan['fixed']['checkpoint_sha256']:
            raise ValueError('baseline config/checkpoint mismatch')
        if meta['calibration']['sha256'] != vio.sha_file(HERE/'calibration_train.json') or meta['map']['sha256'] != vio.sha_file(vio.MAP_FILE):
            raise ValueError('baseline map/calibration mismatch')
        observations,_ = vio.load_obs(vio.PRIMARY_OUT/'r3/obs-w6'/f'{ep}.obs.npz',kind='vision',episode=ep,
            obs_params=vio.config_obs_params(cfg),checkpoint_sha256=plan['fixed']['checkpoint_sha256'],infer_size=cfg['infer_size'])
        last_scan, result = None,[]
        for f,r,(loaded,settled) in zip(frames,rows,own,strict=True):
            if (f['frame'],f['t']) != (r['frame'],r['t']) or loaded!=r['loaded'] or settled!=r['settled']:
                raise ValueError('frame/own-state alignment failure')
            e = r['vision']
            if not e:
                raise ValueError('missing estimate cannot be dropped')
            pose = {int(k):int(v) for k,v in f['commanded_servo'].items()}
            pan = vl.pan_yaw(cal.get('pan_base_yaw',{}),loaded,pose)
            b,dz = vl.sag(cal['sag'],loaded,pose)
            cm = vl.column_model(pose,b,dz,observations[f['frame']].columns,pan)
            localizer = SimpleNamespace(n=plan['fixed']['particles'],
                expected=lambda px,pose:vl.expected_rows(geometry,px,cm),
                measurement={**vl.DEFAULT_MEASUREMENT,**cfg['measurement']},obs_params=vio.config_obs_params(cfg))
            estimate = dict(zip(('x','y','yaw'),e['xyyaw']))
            estimate.update(std_yaw_rad=e['std_yaw_rad'],pan_yaw_offset=pan)
            features = head.features(localizer,estimate,observations[f['frame']],pose,
                measured=bool(e['measured']),ess_pre=(e.get('diag') or {}).get('ess_pre'))
            if e['measured']:
                last_scan = f['t']
            result.append({'frame':f['frame'],'t':f['t'],'loaded':loaded,'settled':settled,
                'skill_phase':r['skill_phase'],'point':e['xyyaw'],'raw_xy_var':e['std_xy_m']**2,
                'raw_yaw_var':e['std_yaw_rad']**2,'last_scan':last_scan,'observation':features})
        jsonl(output/f'{ep}.features.jsonl',result)
        sequences.append({'name':ep,'cohort':'fit' if ep in plan['fit_episodes'] else 'validation','frames':len(result)})
    frames = vl.read_jsonl(cs.VISW/'robots/r2/inputs/frames.jsonl')
    commands = vl.read_jsonl(cs.VISW/'robots/r2/inputs/commands.jsonl')
    own = cs.command_features(frames,commands,cfg['measurement']['settle_s'])
    result=[]
    for f,(loaded,settled) in zip(frames,own,strict=True):
        e=f['report']
        if not e['initialized'] or e['t_est']!=f['t'] or loaded!=(e['load_state']=='loaded'):
            raise ValueError('invalid VISW baseline')
        result.append({'frame':f['frame'],'t':f['t'],'loaded':loaded,'settled':settled,
            'skill_phase':None,'point':e['xyyaw'],'raw_xy_var':e['std_xy_m']**2,'raw_yaw_var':e['std_yaw_rad']**2,
            'last_scan':None if e['last_valid_obs'] is None else e['last_valid_obs']['t'],
            'observation':{'available':False,'yaw_delta':0.}})
    name=plan['visw']['episode']; jsonl(output/f'{name}.features.jsonl',result)
    sequences.append({'name':name,'cohort':'fit_VISW','frames':len(result)})
    mismatch=verify({**sources,**inputs})
    save(output/'feature_manifest.json',{'sequences':sequences,'mismatches':mismatch,
         'features_sha256':{s['name']:vio.sha_file(output/f"{s['name']}.features.jsonl") for s in sequences},
         'scope':'No evaluation GT read in extraction; no new model inference, renders or physics steps',
         'load_average_end':os.getloadavg()})
    if mismatch:
        raise ValueError('frozen inputs changed')


def replay(rows,config):
    h=head.ReportHead(config); out=[]
    for r in rows:
        if not h.config['enabled']:
            values={'xy_var':r['raw_xy_var'],'yaw_var':r['raw_yaw_var'],'yaw_delta':0.,'mode_alarm':False}
        else:
            values=h.step(**{k:r[k] for k in ('raw_xy_var','raw_yaw_var','t','last_scan','loaded','settled','observation')})
        point=list(r['point'])
        if values['yaw_delta']:
            point[2]=math.atan2(math.sin(point[2]+values['yaw_delta']),math.cos(point[2]+values['yaw_delta']))
        out.append({**values,'point':point})
    return out


def errors(rows, values, truth):
    e=np.array([v['point'] for v in values])-np.array([truth[r['frame']]['gt'] for r in rows])
    e[:,2]=np.arctan2(np.sin(e[:,2]),np.cos(e[:,2])); return e


def weights(sequences):
    return np.concatenate([np.full(len(s['rows']),1/len(s['rows'])/len(sequences)) for s in sequences])


def fit_yaw(sequences,refine,plan):
    err=[]; raw=[]; state=[]; age=[]
    for s in sequences:
        vals=replay(s['rows'],{'enabled':True,'refine_yaw':refine})
        err.extend(errors(s['rows'],vals,s['truth'])[:,2])
        raw.extend(r['raw_yaw_var'] for r in s['rows'])
        state.extend(head.STATES.index(head.state_key(r['loaded'],r['settled'])) for r in s['rows'])
        age.extend(0. if r['last_scan'] is None else r['t']-r['last_scan'] for r in s['rows'])
    err,raw,state,age,w=map(np.asarray,(err,raw,state,age,weights(sequences)))
    grid=[(a,math.radians(b)**2) for a in plan['yaw_fit']['variance_a_grid'] for b in plan['yaw_fit']['floor_deg_grid']]
    states,details={},{}
    for j,key in enumerate(head.STATES):
        mask=state==j; fallback=mask.sum()<100
        if fallback: mask=np.ones(len(err),bool)
        def objective(pair):
            a,b=pair; v=np.maximum(a*raw[mask]+b+head.Q*age[mask],1e-12)
            nll=.5*(np.log(2*math.pi*v)+err[mask]**2/v)
            return float(np.sum(w[mask]*nll)/w[mask].sum())
        a,b=min(grid,key=lambda p:(objective(p),p))
        states[key]={'a':a,'b_rad2':b}
        details[key]={'fit_n':int(mask.sum()),'pooled_fallback':bool(fallback),'nll':objective((a,b))}
    return {'enabled':True,'refine_yaw':refine,'yaw_states':states},details


def detector_metrics(sequences,outputs):
    totals=dict(tp=0,fn=0,fp=0,tn=0,alarms=0,frames=0,available_scans=0)
    per={}
    for s,values in zip(sequences,outputs,strict=True):
        e=errors(s['rows'],values,s['truth']); xy=np.linalg.norm(e[:,:2],axis=1); yaw=np.abs(e[:,2])
        lost=(xy>.30)|(yaw>math.radians(10)); normal=(xy<=.10)&(yaw<=math.radians(3))
        alarm=np.array([v['mode_alarm'] for v in values],bool)
        m={'tp':int(np.sum(alarm&lost)),'fn':int(np.sum(~alarm&lost)),
           'fp':int(np.sum(alarm&normal)),'tn':int(np.sum(~alarm&normal)),
           'alarms':int(alarm.sum()),'frames':len(alarm),
           'available_scans':sum(bool(r['observation']['available']) for r in s['rows'])}
        m['recall']=m['tp']/(m['tp']+m['fn']) if m['tp']+m['fn'] else None
        m['normal_fpr']=m['fp']/(m['fp']+m['tn']) if m['fp']+m['tn'] else None
        per[s['name']]=m
        for k in totals: totals[k]+=m[k]
    totals['recall']=totals['tp']/(totals['tp']+totals['fn']) if totals['tp']+totals['fn'] else None
    totals['normal_fpr']=totals['fp']/(totals['fp']+totals['tn']) if totals['fp']+totals['tn'] else None
    # Precision counts all alarm frames (including neither-normal-nor-lost), not only binary extremes.
    totals['precision_lost']=totals['tp']/totals['alarms'] if totals['alarms'] else None
    for key in ('recall','normal_fpr'):
        vals=[m[key] for m in per.values() if m[key] is not None]
        totals['episode_balanced_'+key]=float(np.mean(vals)) if vals else None
    return {'pooled':totals,'episodes':per}


def fit_mode(sequences,y2,plan):
    normal_scores=[]
    for s in sequences:
        # Offline labels define fitting negatives, never a runtime feature.
        e=errors(s['rows'],replay(s['rows'],y2),s['truth'])
        for r,v in zip(s['rows'],e):
            if r['observation']['available'] and np.linalg.norm(v[:2])<=.10 and abs(v[2])<=math.radians(3):
                normal_scores.append(r['observation']['score'])
    if not normal_scores:
        return None,{'rejected':'no fit normal scans'}
    trials=[]
    for q in plan['mode_fit']['threshold_quantiles_normal']:
        threshold=float(np.quantile(normal_scores,q)); cfg={**y2,'mode_threshold':threshold}
        m=detector_metrics(sequences,[replay(s['rows'],cfg) for s in sequences])
        p=m['pooled']; eligible=p['episode_balanced_normal_fpr'] is not None and p['episode_balanced_normal_fpr']<=.05
        trials.append({'quantile':q,'threshold':threshold,'eligible':eligible,'metrics':m})
    valid=[t for t in trials if t['eligible'] and t['metrics']['pooled']['episode_balanced_recall'] is not None]
    best=min(valid,key=lambda t:(-t['metrics']['pooled']['episode_balanced_recall'],
             t['metrics']['pooled']['episode_balanced_normal_fpr'],-t['threshold'])) if valid else None
    return (None if best is None else best['threshold']),{'normal_scan_count':len(normal_scores),'trials':trials}


def events(mask,rows):
    count=0; active=False; max_s=0.; start=0.; prev=None; frames=0; longest=0
    for yes,r in zip(mask,rows,strict=True):
        contiguous=prev is not None and r['frame']==prev['frame']+1 and r['t']-prev['t']<=1.
        if yes:
            if not active or not contiguous: count+=1; start=r['t']; frames=0
            frames+=1; longest=max(longest,frames); max_s=max(max_s,r['t']-start)
        active=bool(yes); prev=r
    return {'events':count,'longest_s':max_s,'longest_frames':longest}


def metrics(rows,values,truth,mask):
    ix=np.flatnonzero(mask)
    if not len(ix): return {'n':0,'status':'EMPTY_GROUP'}
    e=errors(rows,values,truth)[ix]; xy=np.linalg.norm(e[:,:2],axis=1); yaw=np.abs(e[:,2])
    xv=np.maximum([values[i]['xy_var'] for i in ix],1e-12)
    yv=np.maximum([values[i]['yaw_var'] for i in ix],1e-12)
    zxy=xy**2/xv; zy=yaw**2/yv; overxy=zxy>9; overy=zy>9; combined=overxy|overy
    m={'n':len(ix),'xy_nll_iso':float(np.mean(np.log(math.pi*xv)+zxy)),
       'yaw_nll':float(np.mean(.5*(np.log(2*math.pi*yv)+zy))),
       'xy_coverage95_iso':float(np.mean(zxy<=-math.log(.05))),
       'yaw_coverage95':float(np.mean(zy<=3.841458820694124)),
       'xy_over3_fraction':float(np.mean(overxy)),'yaw_over3_fraction':float(np.mean(overy)),
       'overconfident_frames':int(combined.sum()),'overconfident_fraction':float(np.mean(combined)),
       'xy_sigma_p50_m':float(np.median(np.sqrt(xv))),'xy_sigma_p90_m':float(np.quantile(np.sqrt(xv),.9)),
       'yaw_sigma_p50_deg':float(np.degrees(np.median(np.sqrt(yv)))),
       'yaw_sigma_p90_deg':float(np.degrees(np.quantile(np.sqrt(yv),.9))),
       'mode_alarm_frames':sum(values[i]['mode_alarm'] for i in ix),
       'lost_xy_frames':int((xy>.30).sum()),'covariance_scope':'legacy XY isotropic proxy; yaw 1D'}
    for name,a in [('pos',xy),('yaw',np.degrees(yaw))]:
        for label,p in [('p50',.5),('p90',.9),('p99',.99),('max',1.)]:
            m[f'{name}_{label}'+('_m' if name=='pos' else '_deg')]=float(np.quantile(a,p))
    m.update({'overconfident_'+k:v for k,v in events(combined,[rows[i] for i in ix]).items()})
    return m


def masks(s):
    rows=s['rows']; gt=np.array([s['truth'][r['frame']]['gt'] for r in rows])
    load=np.array([r['loaded'] for r in rows],bool)
    return {'all':np.ones(len(rows),bool),
        'door_loaded':load&(np.abs(gt[:,0]-2.2)<.6)&(gt[:,1]>-.45)&(gt[:,1]<.55),
        'loaded_transport':load&np.array([r['skill_phase']=='nav_preplace' or s['cohort']=='fit_VISW' for r in rows],bool)}


def summarize(sequences,outputs):
    per={}
    for s,v in zip(sequences,outputs,strict=True):
        per[s['name']]={g:metrics(s['rows'],v,s['truth'],mask) for g,mask in masks(s).items()}
        if s['cohort']=='fit_VISW':
            for name,lo,hi in [('grasp_90_150',90,150),('near_A_430_462',430,462)]:
                mask=np.array([lo<=r['t']<=hi for r in s['rows']]); per[s['name']][name]=metrics(s['rows'],v,s['truth'],mask)
    cohorts={}
    for cohort in ('fit','validation','all_teacher','fit_VISW'):
        chosen=[(s,v) for s,v in zip(sequences,outputs,strict=True)
                if s['cohort']==cohort or (cohort=='all_teacher' and s['cohort']!='fit_VISW')]
        if not chosen: continue
        result={}
        for group in ('all','door_loaded','loaded_transport'):
            rows=[]; values=[]; truth={}; offset=0
            # Unique artificial frame indices/time gaps stop events bridging episodes.
            for s,v in chosen:
                for i in np.flatnonzero(masks(s)[group]):
                    r=dict(s['rows'][i]); original=r['frame']; r['frame']=offset+original
                    rows.append(r); values.append(v[i]); truth[r['frame']]=s['truth'][original]
                offset+=len(s['rows'])+100000
            m=metrics(rows,values,truth,np.ones(len(rows),bool))
            valid=[per[s['name']][group] for s,_ in chosen if per[s['name']][group]['n']]
            if m['n']:
                for k in ('yaw_nll','xy_nll_iso'):
                    m['episode_balanced_'+k]=float(np.mean([p[k] for p in valid]))
                m['episodes_with_frames']=len(valid); m['episodes_total']=len(chosen)
            result[group]=m
        cohorts[cohort]=result
    return {'episodes':per,'cohorts':cohorts}


def select(results,detector,threshold,plan):
    b=results['b0u0']; checks={}; eligible=[]
    for name in ('y1','s1','y2','m1'):
        c=results[name]; reasons=[]
        for cohort in ('validation','all_teacher'):
            for group in ('door_loaded','loaded_transport'):
                bm,cm=b['cohorts'][cohort][group],c['cohorts'][cohort][group]
                if not cm['n']: reasons.append(f'{cohort}/{group}:missing'); continue
                if cm['pos_p90_m']>bm['pos_p90_m']+.003+1e-12: reasons.append(f'{cohort}/{group}:position_regression')
                if cm['yaw_p90_deg']>bm['yaw_p90_deg']+.3+1e-12: reasons.append(f'{cohort}/{group}:yaw_regression')
        for ep in plan['validation_episodes']:
            bm,cm=b['episodes'][ep]['all'],c['episodes'][ep]['all']
            if cm['yaw_p90_deg']>bm['yaw_p90_deg']+.5+1e-12: reasons.append(f'{ep}:yaw_regression')
            if name!='y1' and cm['yaw_nll']>bm['yaw_nll']+.10: reasons.append(f'{ep}:yaw_nll_regression')
        bm,cm=b['cohorts']['validation']['all'],c['cohorts']['validation']['all']
        if name=='y1':
            for cohort in ('validation','all_teacher'):
                bb,cc=b['cohorts'][cohort]['door_loaded'],c['cohorts'][cohort]['door_loaded']
                if cc['yaw_p90_deg']>bb['yaw_p90_deg']-.1+1e-12: reasons.append(f'{cohort}:yaw_not_improved_0.1deg')
            if cm['yaw_over3_fraction']>bm['yaw_over3_fraction']: reasons.append('yaw_over3_regression')
        else:
            if cm['episode_balanced_yaw_nll']>bm['episode_balanced_yaw_nll']-.05: reasons.append('yaw_nll_not_improved')
            for group in ('all','door_loaded','loaded_transport'):
                m=c['cohorts']['validation'][group]
                if not .90<=m['yaw_coverage95']<=.99: reasons.append(f'{group}:yaw_coverage')
                if m['yaw_over3_fraction']>.01: reasons.append(f'{group}:yaw_over3')
            if cm['yaw_sigma_p90_deg']>5: reasons.append('yaw_sigma_overinflation')
            if cm['overconfident_events']>bm['overconfident_events']: reasons.append('event_regression')
        if cm['overconfident_fraction']>bm['overconfident_fraction']: reasons.append('overconfidence_regression')
        if name=='m1':
            # m1 must also satisfy y2 eligibility; reported as an explicit dependency.
            if not checks['y2']['eligible']: reasons.append('y2_ineligible')
            m=detector['validation']['pooled']
            if threshold is None: reasons.append('no_fit_detector')
            if m['recall'] is None or m['recall']<.5: reasons.append('detector_recall')
            if m['normal_fpr'] is None or m['normal_fpr']>.05: reasons.append('detector_false_positive')
            if not .90<=cm['xy_coverage95_iso']<=.99: reasons.append('xy_coverage')
            if cm['xy_over3_fraction']>.01: reasons.append('xy_over3')
            if cm['episode_balanced_xy_nll_iso']>bm['episode_balanced_xy_nll_iso']-.05: reasons.append('xy_nll_not_improved')
            if cm['xy_sigma_p50_m']>.1: reasons.append('xy_sigma_overinflation')
            if cm['overconfident_frames']>=bm['overconfident_frames'] or cm['overconfident_events']>=bm['overconfident_events']:
                reasons.append('overconfidence_not_strictly_reduced')
        checks[name]={'eligible':not reasons,'reasons':reasons}
        if not reasons: eligible.append(name)
    def rank(name):
        m=results[name]['cohorts']['validation']; a=m['all']; g=m['door_loaded']
        return g['pos_p90_m'],g['yaw_p90_deg'],a['overconfident_frames'],a['episode_balanced_yaw_nll'],list(checks).index(name)
    return {'shadow_selected':min(eligible,key=rank) if eligible else 'b0u0','default':'b0/u0',
            'deployment_enabled':False,'checks':checks,'scope':'dev shadow report-head only; no independent test or physical validation'}


def audit_routes(sequences,all_outputs):
    rects=vl._rects(vl.mp.MapGeometry(vio.load_map(),include_posts=False))
    geometry_cache={}; out={}
    for variant,outputs in all_outputs.items():
        per={}; segments_all=[]
        for s,values in zip(sequences,outputs,strict=True):
            if s['cohort']=='fit_VISW': continue
            mask=masks(s)['loaded_transport']; rows=s['rows']; segments=[]
            for i in range(1,len(rows)):
                if not mask[i-1] or not mask[i] or rows[i]['frame']!=rows[i-1]['frame']+1 or rows[i]['t']-rows[i-1]['t']>1:
                    continue
                start,end=values[i-1]['point'],values[i]['point']; key=tuple(start+end)
                if key not in geometry_cache: geometry_cache[key]=route.swept_clearance(start,end,rects)
                geom=geometry_cache[key]
                xy=math.sqrt(max(values[i-1]['xy_var'],values[i]['xy_var']))
                yaw=math.sqrt(max(values[i-1]['yaw_var'],values[i]['yaw_var']))
                budget=3*xy+.5*math.sin(min(math.pi,3*yaw)/2)+.015
                segments.append({'frame_start':rows[i-1]['frame'],'frame_end':rows[i]['frame'],
                    **geom,'budget_m':budget,'adjusted_lower_m':geom['footprint_lower_m']-budget})
            per[s['name']]={'segments':len(segments),'worst':min(segments,key=lambda r:r['adjusted_lower_m']) if segments else None,
                'geometric_6cm_fail':sum(v['footprint_lower_m']<.06 for v in segments),
                'sigma_clearance_fail':sum(v['adjusted_lower_m']<0 for v in segments)}
            segments_all.extend(segments)
        out[variant]={'episodes':per,'segments':len(segments_all),
            'geometric_6cm_fail':sum(v['footprint_lower_m']<.06 for v in segments_all),
            'sigma_clearance_fail':sum(v['adjusted_lower_m']<0 for v in segments_all),
            'min_adjusted_lower_m':min((v['adjusted_lower_m'] for v in segments_all),default=None),
            'status':'ROUTE_CONTRACT_UNMET' if any(v['adjusted_lower_m']<0 or v['footprint_lower_m']<.06 for v in segments_all) else 'INSUFFICIENT_PLANNED_ROUTE_PROVENANCE'}
    return {'variants':out,'scope':plan_load()['route_audit'],'new_physics_steps':0,
            'limitation':'Audit is of estimated shadow polylines. Planned route and actual swept path are not interchangeable; no safety/physical passage claim.'}


def compare(output):
    plan=plan_load(); freeze=vio.load_json(output/'source_freeze.json'); manifest=vio.load_json(output/'feature_manifest.json')
    expected=plan['fit_episodes']+plan['validation_episodes']+[plan['visw']['episode']]
    if [s['name'] for s in manifest['sequences']]!=expected or manifest['mismatches']:
        raise ValueError('incomplete, reordered or inconsistent dev cohort')
    if verify({**freeze['sources'],**freeze['inputs']}) or freeze['plan_sha256']!=vio.sha_file(PLAN):
        raise ValueError('source/input changed since extraction')
    sources={}; sequences=[]
    for info in manifest['sequences']:
        name=info['name']; path=output/f'{name}.features.jsonl'
        if vio.sha_file(path)!=manifest['features_sha256'][name]: raise ValueError('feature hash changed')
        rows=vl.read_jsonl(path)
        gt_path=(cs.VISW if info['cohort']=='fit_VISW' else vio.RENDER_ROOT/name)/'eval_only/frames_eval.jsonl'
        sources[str(gt_path)]=vio.sha_file(gt_path)
        truth={r['frame']:r for r in vl.read_jsonl(gt_path) if info['cohort']!='fit_VISW' or r['robot_id']=='r2'}
        if len(rows)!=info['frames'] or len(truth)!=len(rows): raise ValueError('incomplete evaluation sequence')
        for r in rows:
            if r['frame'] not in truth or abs(r['t']-truth[r['frame']]['t'])>1e-7: raise ValueError('evaluation alignment')
        sequences.append({**info,'rows':rows,'truth':truth})
    save(output/'evaluation_input_hashes.json',sources)
    training=[s for s in sequences if s['cohort']=='fit']
    s1,s1fit=fit_yaw(training+[s for s in sequences if s['cohort']=='fit_VISW'],False,plan)
    y2,y2fit=fit_yaw(training,True,plan)
    threshold,modefit=fit_mode(training,y2,plan)
    configs={'b0u0':{'enabled':False},'y1':{'enabled':True,'refine_yaw':True},'s1':s1,'y2':y2,
             'm1':{**y2,'mode_threshold':threshold}}
    save(output/'fit.json',{'configs':configs,'s1':s1fit,'y2':y2fit,'mode':modefit,'plan_sha256':vio.sha_file(PLAN),
        'fit_only_episodes':[s['name'] for s in training],'s1_additional_fit_VISW':plan['visw']['episode']})
    results,all_outputs={},{}
    # No validation value above was passed to any fitting function.
    for name,config in configs.items():
        chosen=[s for s in sequences if s['cohort']!='fit_VISW' or name in ('b0u0','s1')]
        values=[replay(s['rows'],config) for s in chosen]
        results[name]=summarize(chosen,values)
        all_outputs[name]=values
        jsonl(output/f'{name}.reports.jsonl',[{'episode':s['name'],'frame':r['frame'],'t':r['t'],**v}
              for s,vv in zip(chosen,values,strict=True) for r,v in zip(s['rows'],vv,strict=True)])
    teachers=[s for s in sequences if s['cohort']!='fit_VISW']
    detector={}
    for cohort in ('fit','validation','all_teacher'):
        pairs=[(s,v) for s,v in zip(teachers,all_outputs['m1'],strict=True) if s['cohort']==cohort or cohort=='all_teacher']
        detector[cohort]=detector_metrics([s for s,_ in pairs],[v for _,v in pairs])
    save(output/'detector.json',{'cohorts':detector,'VISW':'UNAVAILABLE: no residual cache or pre-resampling ESS'})
    decision=select(results,detector,threshold,plan)
    save(output/'metrics.json',results); save(output/'selection.json',decision)
    print(json.dumps(decision),flush=True)
    # VISW appended last; only teacher paths have the nav_preplace contract.
    audit=audit_routes(teachers,{k:v[:len(teachers)] for k,v in all_outputs.items()})
    save(output/'route_audit.json',audit)
    mismatch=verify({**freeze['sources'],**freeze['inputs'],**sources})
    save(output/'verification.json',{'mismatches':mismatch,'source_files':len(freeze['sources']),
        'input_files':len(freeze['inputs'])+len(sources),'teacher_episodes':len(teachers),
        'teacher_frames':sum(len(s['rows']) for s in teachers),'VISW_frames':len(sequences[-1]['rows']),
        'test_episodes_read':0,'new_model_calls':0,'new_renders':0,'physics_steps':0,
        'student_runtime_truth_fields':0,'legacy_full_covariance_available':False,'load_average_end':os.getloadavg()})
    if mismatch: raise ValueError('integrity failure')


def main():
    ap=argparse.ArgumentParser(description=__doc__); action=ap.add_mutually_exclusive_group(required=True)
    action.add_argument('--extract',action='store_true'); action.add_argument('--compare',action='store_true')
    ap.add_argument('--output',type=Path,default=OUT); args=ap.parse_args()
    if args.extract: extract(args.output)
    else: compare(args.output)


if __name__=='__main__': main()
