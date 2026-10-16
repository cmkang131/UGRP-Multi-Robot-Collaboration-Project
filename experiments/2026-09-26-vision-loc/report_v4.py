#!/usr/bin/env python3
"""Final dev-only evidence summary and native TensorBoard snapshot for VIS4."""
import json
import math
from pathlib import Path
import sys
import time
import urllib.parse

import numpy as np

import diagnose_v4 as d
import vision_loc as vl
import vision_loc_io as vio

sys.path.insert(0, str(d.HERE.parents[1]))


def signed_metrics(directory, episodes):
    values = {'vision': [], 'oracle': []}
    scale = {k:[] for k in values}
    for ep in episodes:
        gt={r['frame']:r['gt'] for r in vl.read_jsonl(vio.RENDER_ROOT/ep/'eval_only'/'frames_eval.jsonl')}
        for r in vl.read_jsonl(directory/f'{ep}.estimates.jsonl'):
            g=gt[r['frame']]
            if not r['loaded'] or abs(g[0]-2.2)>=.6 or not -.45<g[1]<.55: continue
            for kind in values:
                e=r[kind]['xyyaw']; dx,dy=e[0]-g[0],e[1]-g[1]
                dyaw=math.degrees(math.atan2(math.sin(e[2]-g[2]),math.cos(e[2]-g[2])))
                values[kind].append([dx,dy,dyaw,math.cos(g[2])*dx+math.sin(g[2])*dy])
                if (r[kind].get('diag') or {}).get('scale_mean'):
                    scale[kind].append(r[kind]['diag']['scale_mean'])
    return {k:{**d.error_summary(v),'particle_scale_mean':np.mean(scale[k],axis=0).tolist() if scale[k] else None}
            for k,v in values.items()}


def main():
    from scripts.tensorboard_tools.export import Writer
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
    from tensorboard.plugins.hparams import metadata, plugin_data_pb2
    plan=vio.load_json(d.PLAN); cmp=d.OUT/'comparison'; selection=vio.load_json(cmp/'selection.json')
    if not selection or (cmp/'INCOMPLETE.json').exists(): raise SystemExit('complete comparison required')
    eps=plan['fit_episodes']+plan['validation_episodes']; d.require_dev(eps)
    report={'selection':{k:v for k,v in selection.items() if k!='metrics'},'variants':{},'source_sha256':{},
            'scope':'Offline dev replay only; baseline reused; no new RGB inference, simulation, test or task success.',
            'new_segmentation_calls':0,'new_llm_calls':0,'new_robot_commands':0,
            'original_raw_root':str(vio.PRIMARY_OUT),'worktree_output':str(d.OUT)}
    snapshot=d.OUT/'tensorboard'/'0927-vis4-dev'
    snapshot.mkdir(parents=True,exist_ok=False)
    expected=[]; expected_hparams={}; runs=[]
    pins=['summary/door_loaded/pos_p90_m','summary/door_loaded/lat_abs_p99_m','summary/door_loaded/yaw_p90_deg',
          'summary/all/pos_p90_m','recovery/lost_frames','diagnosis/forward_mean_m',
          'inputs/recorded_commands','compute/replay_wall_s','compute/new_model_calls']
    for variant in ('b0','x1','m1'):
        signed=signed_metrics(cmp/variant,eps)
        report['variants'][variant]={'signed_door_loaded':signed}
        for cohort in ('all_dev','validation'):
            metrics=selection['metrics'][variant][cohort]
            cohort_eps=eps if cohort=='all_dev' else plan['validation_episodes']
            cohort_signed=signed if cohort=='all_dev' else signed_metrics(cmp/variant,cohort_eps)
            report['variants'][variant][f'{cohort}_signed_door_loaded']=cohort_signed
            source=cmp/variant/f'metrics_{cohort}.json'
            report['source_sha256'][str(source)]=vio.sha_file(source)
            for kind in ('vision','oracle'):
                name=f'{variant}-{cohort}-{kind}'; run=snapshot/name; run.mkdir()
                w=Writer(run,time.time()); numbers={}
                for group in ('all','door_loaded'):
                    for key,value in metrics['pooled'][kind][group].items():
                        if isinstance(value,(int,float)):
                            numbers[f'summary/{group}/{key}']=value
                numbers['recovery/lost_frames']=metrics['recovery_pooled'][kind]['lost_frames']
                numbers['inputs/recorded_commands']=sum(len(vl.read_jsonl(vio.RENDER_ROOT/e/'inputs'/'commands.jsonl'))
                                                        for e in cohort_eps)
                numbers['compute/new_model_calls']=0  # cached columns, not new segmentation/LLM inference
                if variant!='b0':
                    numbers['compute/replay_wall_s']=sum(vio.load_json(cmp/variant/f'{e}.meta.json')['wall_s']
                                                         for e in cohort_eps)  # both sinks together, not per-filter speed
                numbers['diagnosis/forward_mean_m']=cohort_signed[kind]['forward_mean_m']
                for tag,value in numbers.items(): w.scalar(tag,float(value)); expected.append((name,tag,float(value)))
                w.text('provenance/source',{'metrics':str(source),'sha256':vio.sha_file(source),
                     'baseline_reused':variant=='b0','scope':report['scope'],'oracle_diagnostic':kind=='oracle',
                     'wall_scope':'both vision and oracle replay together under observed host load; not a speed benchmark',
                     'commands_scope':'recorded original commands replayed; no newly issued robot commands'})
                w.text('selection/decision',{'selected':selection['selected'],
                     'candidate_check':selection['checks'].get(variant),
                     'rule':str(d.PLAN),'plan_sha256':selection['plan_sha256'],
                     'note':'Development selection only. Baseline fallback is not a gate pass or task success.'})
                hparams={'variant':variant,'filter':kind,'cohort':cohort,'split':'dev','environment':'tagfree-v3',
                         'particles':2000,'model_sha8':plan['fixed']['segmentation_sha256'][:8],
                         'source':'VIS3 a1 reused' if variant=='b0' else '1aa8f0c7+uncommitted-VIS4'}
                w.hparams(hparams,pins); expected_hparams[name]={k:str(v) for k,v in hparams.items()}
                w.close(); runs.append({'name':name,'source':str(source),'kind':'completed_dev_summary'})
    for source in ('diagnosis.json','likelihood.json','motion_fit_final.json','motion_residuals.json','camera_residuals.json',
                   'posthoc_x1_s945.json','cargo_state_v4.json','baseline_meta_audit.json'):
        report['source_sha256'][str(d.OUT/source)]=vio.sha_file(d.OUT/source)
    d.save(snapshot/'collection.json',{'schema':'ugrp.vis4.tensorboard.v1','exported':runs,'source_sha256':report['source_sha256'],
                                    'scope':report['scope'],'videos':[],'videos_note':'No new render/video created; reused original recordings remain read-only.'})
    accum={name:EventAccumulator(str(snapshot/name)).Reload() for name in [r['name'] for r in runs]}
    mismatches=[]
    for name,tag,value in expected:
        got=accum[name].Scalars(tag)[0].value
        if not math.isclose(got,value,rel_tol=1e-6,abs_tol=1e-7): mismatches.append([name,tag,value,got])
    for name,values in expected_hparams.items():
        data=plugin_data_pb2.HParamsPluginData.FromString(
            accum[name].SummaryMetadata(metadata.SESSION_START_INFO_TAG).plugin_data.content)
        got={k:v.string_value for k,v in data.session_start_info.hparams.items()}
        if got!=values: mismatches.append([name,'hparams',values,got])
    verification={'runs':len(runs),'scalars_checked':len(expected),'mismatches':mismatches,'actual_event_loading':True,
                  'hparams_runs_checked':len(expected_hparams),
                  'dashboard_display_verified':False,'shared_primary_root_updated':False}
    d.save(d.OUT/'tensorboard_verification.json',verification)
    url='http://127.0.0.1:6016/?'+urllib.parse.urlencode({'pinnedCards':json.dumps([{'plugin':'scalars','tag':t} for t in pins]),
             'smoothing':'0','runFilter':'^'})+'#timeseries'
    d.save(d.OUT/'tensorboard-view.json',{'active_logdir':str(snapshot),'url':url,'pinned_tags':pins,
            'hparams_visible_columns':['variant','filter','cohort','split','environment','particles','model_sha8'],
            'server_started':False,'shared_primary_root':'/Users/changmin/projects/ugrp/outputs/tensorboard',
            'scope':'Worktree snapshot per user output constraint; shared-root publication not performed.'})
    report['tensorboard']=verification
    d.save(d.OUT/'report.json',report)
    print(json.dumps({'selection':report['selection'],'variants':report['variants'],'tensorboard':verification},indent=1))
    if mismatches: raise SystemExit('TensorBoard scalar verification failed')


if __name__=='__main__': main()
