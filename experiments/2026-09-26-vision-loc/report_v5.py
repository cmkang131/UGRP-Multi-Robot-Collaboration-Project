#!/usr/bin/env python3
"""Export completed VIS5 evidence to native TensorBoard, verify every scalar."""
import json
import sys
import time
import urllib.parse
from pathlib import Path

import numpy as np

import compare_v5 as c
import record_verify as rv
import vision_loc_io as vio

sys.path.insert(0,str(c.HERE.parents[1]))


def main():
    from scripts.tensorboard_tools.export import Writer
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
    from tensorboard.plugins.hparams import metadata,plugin_data_pb2

    out=c.OUT/'final'
    verification=vio.load_json(out/'verification.json')
    if verification['mismatches']:
        raise ValueError('incomplete/inconsistent comparison')
    freeze=vio.load_json(out/'source_freeze.json')
    if c.verify({**freeze['inputs'],**vio.load_json(out/'evaluation_input_hashes.json')}):
        raise ValueError('frozen evidence changed')
    # Sources moved to vision_pf_v5.py / vision_loc_cli_v5.py (2026-09-28): check the recording commit's blobs.
    if rv.blob_mismatches(freeze['sources'],rv.VIS5_FINAL_RECORD_COMMIT):
        raise ValueError('frozen sources changed')
    results=vio.load_json(out/'metrics.json'); decision=vio.load_json(out/'selection.json')
    detector=vio.load_json(out/'detector.json'); route=vio.load_json(out/'route_audit.json')
    snapshot=out/'tensorboard/0927-vis5-dev'; snapshot.mkdir(parents=True,exist_ok=False)
    pins=['summary/door_loaded/pos_p90_m','summary/door_loaded/yaw_p90_deg',
          'summary/all/yaw_coverage95','summary/all/yaw_over3_fraction',
          'summary/all/xy_coverage95_iso','summary/all/xy_over3_fraction',
          'summary/all/overconfident_frames','summary/all/overconfident_events',
          'summary/all/yaw_sigma_p90_deg','compute/new_model_calls']
    expected={}; hp_expected={}; runs=[]
    for variant,data in results.items():
        for cohort,groups in data['cohorts'].items():
            name=f'{variant}-{cohort}'; path=snapshot/name; path.mkdir(); w=Writer(path,time.time())
            values={f'summary/{g}/{k}':float(v) for g,m in groups.items() for k,v in m.items()
                    if type(v) in (int,float)}
            values.update({'compute/new_model_calls':0.,'compute/new_renders':0.,'compute/new_physics_steps':0.,
                           'compute/new_commands':0.})
            if cohort in detector['cohorts'] and variant=='m1':
                values.update({f'detector/{k}':float(v) for k,v in detector['cohorts'][cohort]['pooled'].items()
                               if type(v) in (int,float)})
            if cohort=='all_teacher':
                values.update({f'route/{k}':float(v) for k,v in route['variants'][variant].items()
                               if type(v) in (int,float)})
            for k,v in values.items(): w.scalar(k,v)
            h={'variant':variant,'cohort':cohort,'split':'dev','mode':'report_head_shadow',
               'default':'b0/u0','selected':decision['shadow_selected'],'xy_cov':'isotropic_proxy'}
            w.hparams(h,pins)
            w.text('provenance',{'metrics':str(out/'metrics.json'),'metrics_sha256':vio.sha_file(out/'metrics.json'),
                'plan_sha256':vio.sha_file(c.PLAN),'new_model_calls':0,'new_physics_steps':0,
                'scope':'Saved dev observations. Report-head changes do not feed the PF. No test, physical completion or success metric.',
                'VISW':'fit only; no scan-cache yaw refinement/detector evaluation',
                'source_commit':freeze['base_sha'],'uncommitted_changes':True})
            w.close(); expected[name]=values; hp_expected[name]=h; runs.append({'name':name,'completed':True})
    mismatches=[]; count=0
    for name,values in expected.items():
        acc=EventAccumulator(str(snapshot/name),size_guidance={'scalars':0}).Reload()
        if set(acc.Tags()['scalars'])!=set(values): mismatches.append([name,'scalar_tags'])
        for tag,v in values.items():
            events=acc.Scalars(tag); count+=1
            if len(events)!=1 or not np.isclose(events[0].value,v,rtol=1e-6,atol=1e-7): mismatches.append([name,tag])
        hp=plugin_data_pb2.HParamsPluginData.FromString(acc.SummaryMetadata(metadata.SESSION_START_INFO_TAG).plugin_data.content)
        if {k:v.string_value for k,v in hp.session_start_info.hparams.items()}!=hp_expected[name]:
            mismatches.append([name,'hparams'])
    c.save(snapshot/'collection.json',{'schema':'ugrp.vis5.tensorboard.v1','exported':runs,
        'source_sha256':{str(out/'metrics.json'):vio.sha_file(out/'metrics.json'),str(c.PLAN):vio.sha_file(c.PLAN),
                         str(Path(__file__).resolve()):vio.sha_file(Path(__file__))},
        'videos':[],'scope':'completed dev-only shadow evaluation; no new video'})
    shared=Path('/Users/changmin/projects/ugrp/outputs/tensorboard')
    url='http://127.0.0.1:6006/?'+urllib.parse.urlencode({'runFilter':'^0927-vis5-dev/',
        'pinnedCards':json.dumps([{'plugin':'scalars','tag':tag} for tag in pins]),'smoothing':'0'})+'#timeseries'
    c.save(out/'tensorboard-view.json',{'active_logdir':str(shared),'local_snapshot':str(snapshot),
        'proposed_shared_snapshot':str(shared/snapshot.name),'url_after_shared_registration':url,
        'pinned_tags':pins,'hparams_visible_columns':['variant','cohort','mode','default','selected','xy_cov'],
        'shared_registration_complete':False,'server_ownership_verified':False,'display_verified':False,
        'blocker':'primary checkout is outside writable roots; /bin/ps denied by sandbox. Existing server untouched.',
        'new_videos':0})
    check={'actual_event_loading':True,'runs':len(runs),'scalars_checked':count,
           'hparams_checked':len(runs),'mismatches':mismatches,'display_verified':False,
           'shared_registration_complete':False}
    c.save(out/'tensorboard_verification.json',check); print(json.dumps(check),flush=True)
    if mismatches: raise ValueError('TensorBoard reload mismatch')


if __name__=='__main__': main()
