#!/usr/bin/env python3
"""Read-only VISW yaw/gate diagnosis and native TensorBoard plots."""
import hashlib
import json
import math
from pathlib import Path
from statistics import NormalDist
import subprocess
import sys
import time
import urllib.parse

import numpy as np

import calibrate_sigma_v4 as cs
import diagnose_v4 as d
import record_verify as rv
import vision_loc_io as vio

sys.path.insert(0, str(d.HERE.parents[1]))


def main():
    from scripts.tensorboard_tools.export import Writer
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
    from tensorboard.plugins.hparams import metadata, plugin_data_pb2

    out = d.OUT/'sigma'; results = vio.load_json(out/'metrics.json')
    verification = vio.load_json(out/'verification.json')
    if verification['mismatches']: raise ValueError('source/input integrity failure')
    hashes = vio.load_json(out/'input_hashes.json')
    if any(vio.sha_file(Path(p)) != sha for p, sha in hashes.items()): raise ValueError('frozen inputs changed')
    # Sources moved to vision_pf_v4.py / vision_loc_cli_v4.py (2026-09-28): check the recording commit's blobs.
    sources = vio.load_json(out/'source_freeze.json')['source_sha256']
    if rv.blob_mismatches(sources, rv.VIS4_SIGMA_RECORD_COMMIT): raise ValueError('frozen sources changed')
    data, inputs = cs.load_data(vio.load_json(cs.PLAN))
    visw = next(s for s in data if s['cohort'] == 'fit_VISW')
    a = visw['a']; variance = {}
    for name in results:
        with np.load(out/f'{name}_variance.npz') as z: variance[name] = {k:z[k] for k in z.files}
    vkey = visw['name']+'_vision'
    frames = [json.loads(x) for x in (cs.VISW/'robots/r2/inputs/frames.jsonl').read_text().splitlines()]
    events = [json.loads(x) for x in (cs.VISW/'robots/r2/executor/events.jsonl').read_text().splitlines()]
    gate_rows = []
    for e in events:
        if e['event'] != 'pose_uncertain': continue
        f = min(frames, key=lambda f: abs(f['t']-e['sim_s']))
        rep = f['report']
        if abs(f['t']-e['sim_s']) > .001: raise ValueError('event/frame alignment')
        gate_rows.append({'event_t': e['sim_s'], 'frame_t': f['t'], 'frame': f['frame'],
                         'std_xy_m': rep['std_xy_m'], 'std_yaw_deg': math.degrees(rep['std_yaw_rad']),
                         'xy_above_007': rep['std_xy_m'] > .07,
                         'yaw_above_3deg': rep['std_yaw_rad'] > math.radians(3.),
                         'scan_age_s': rep['since_tag_s'], 'ends_job': e['detail']['ends_job']})
    code_sha = '93936d3655f1ea8e65d12a9b89f6a2d078f89eab'
    gate_sources = {}
    for path in ('harness/m1_owncam_delivery.py', 'harness/zone_own_guards.py'):
        raw = subprocess.check_output(['git','show',f'{code_sha}:{path}'],cwd=cs.HERE)
        gate_sources[code_sha+':'+path] = hashlib.sha256(raw).hexdigest()
    yaw, z95 = {}, NormalDist().inv_cdf(.975)
    for name, mask in [('all',np.ones(len(a),bool)),('grasp_90_150',(a[:,1]>=90)&(a[:,1]<=150)),
                       ('near_A_430_462',(a[:,1]>=430)&(a[:,1]<=462))]:
        b=a[mask]; ratio=b[:,6]/np.maximum(b[:,7],1e-10)
        age=b[:,1]-np.nan_to_num(b[:,2],nan=0.)
        yaw[name]={'n':len(b), 'NEES_yaw_mean':float(np.mean(ratio**2)),
                   'coverage95_1D':float(np.mean(ratio<=z95)), 'over_3sigma':float(np.mean(ratio>3)),
                   'error_p50_deg':float(np.degrees(np.median(b[:,6]))),
                   'sigma_p50_deg':float(np.degrees(np.median(b[:,7]))),
                   'error_p90_deg':float(np.degrees(np.quantile(b[:,6],.9))),
                   'sigma_p90_deg':float(np.degrees(np.quantile(b[:,7],.9))),
                   'fresh_le_025s_frames':int(np.sum(age<=.25)),
                   'fresh_xy_over_3sigma_frames':int(np.sum((age<=.25)&(b[:,5]>9*b[:,4])))}
    d.save(out/'visw_gate_diagnosis.json', {'source_commit':code_sha,'gate_sources_sha256':gate_sources,
           'events':gate_rows,'yaw':yaw,'conclusion':'All 8 pose_uncertain events exceed yaw 3deg, none exceeds XY .07m. XY calibration alone cannot fix that gate.',
           'scope':'Offline diagnosis of recorded reports; no counterfactual closed-loop success claim; no yaw coefficient fitted.'})

    snapshot=d.OUT/'tensorboard'/'0927-vis4-sigma'; snapshot.mkdir(parents=True,exist_ok=False)
    expected={}; expected_hp={}; runs=[]
    pins=['calibration/coverage95','calibration/over_3sigma_fraction','calibration/nees_iso_mean',
          'calibration/episode_balanced_nll_iso','calibration/sigma_p50_m','VISW/error_xy_m','VISW/sigma_xy_m',
          'VISW/yaw_error_deg','VISW/yaw_sigma_deg','compute/new_model_calls']
    for variant, result in results.items():
        for cohort_kind, m in result['cohorts'].items():
            cohort,kind=cohort_kind.split('/'); name=f'{variant}-{cohort}-{kind}'
            path=snapshot/name; path.mkdir(); w=Writer(path,time.time()); expected[name]={}
            for key,value in {**{f'calibration/{k}':v for k,v in m.items()},
                              'compute/new_model_calls':0,'compute/new_commands':0,'compute/new_physics_runs':0}.items():
                w.scalar(key,float(value)); expected[name][key]=[float(value)]
            if cohort=='fit_VISW':
                series={'VISW/error_xy_m':np.sqrt(a[:,5]),'VISW/sigma_xy_m':np.sqrt(variance[variant][vkey]),
                        'VISW/radius95_iso_m':np.sqrt(-math.log(.05)*variance[variant][vkey]),
                        'VISW/yaw_error_deg':np.degrees(a[:,6]),'VISW/yaw_sigma_deg':np.degrees(a[:,7]),
                        'VISW/sim_time_s':a[:,1], 'VISW/scan_age_s':a[:,1]-np.nan_to_num(a[:,2],nan=0.)}
                for tag,values in series.items():
                    for step,value in enumerate(values): w.scalar(tag,float(value),step=step)
                    expected[name][tag]=values.tolist()
            hp={'variant':variant,'cohort':cohort,'filter':kind,'split':'dev','method':'covariance_report_only',
                'xy_nees':'isotropic_proxy','selection':'u0 retained; u1/u2 rejected'}
            w.hparams(hp,pins); expected_hp[name]={k:str(v) for k,v in hp.items()}
            w.text('provenance',{'source':str(out/'metrics.json'),'sha256':vio.sha_file(out/'metrics.json'),
                    'plan':str(cs.PLAN),'plan_sha256':vio.sha_file(cs.PLAN),'new_physics':False,
                    'scope':'Cached DEV replay of covariance head only; same point estimates. VISW is fitting data, not independent test.',
                    'yaw_calibration':'unchanged; diagnostic only','covariance':'legacy trace-only; isotropic XY proxy, not exact NEES',
                    'wall_time':'event export time; never simulation or runtime speed evidence'})
            w.close(); runs.append({'name':name,'source':str(out/'metrics.json'),'kind':'completed_dev_sigma'})
    mismatch=[]; count=0
    for name,tags in expected.items():
        accumulator=EventAccumulator(str(snapshot/name),size_guidance={'scalars':0}).Reload()
        for tag,want in tags.items():
            got=[e.value for e in accumulator.Scalars(tag)]; count+=len(want)
            if len(got)!=len(want) or not np.allclose(got,want,rtol=1e-6,atol=1e-7): mismatch.append([name,tag])
        hp=plugin_data_pb2.HParamsPluginData.FromString(accumulator.SummaryMetadata(metadata.SESSION_START_INFO_TAG).plugin_data.content)
        got={k:v.string_value for k,v in hp.session_start_info.hparams.items()}
        if got!=expected_hp[name]: mismatch.append([name,'hparams'])
    d.save(snapshot/'collection.json',{'schema':'ugrp.vis4.sigma.tensorboard.v1','exported':runs,
           'source_sha256':{str(out/'metrics.json'):vio.sha_file(out/'metrics.json'),str(cs.PLAN):vio.sha_file(cs.PLAN)},
           'videos':[],'scope':'completed offline dev calibration comparison; all candidates rejected'})
    url='http://127.0.0.1:6016/?'+urllib.parse.urlencode({'pinnedCards':json.dumps([{'plugin':'scalars','tag':t} for t in pins]),'smoothing':'0'})+'#timeseries'
    d.save(out/'tensorboard-view.json',{'active_logdir':str(snapshot),'url':url,'pinned_tags':pins,
           'hparams_visible_columns':['variant','cohort','filter','method','xy_nees','selection'],
           'server_started':False,'dashboard_display_verified':False,
           'shared_primary_root_updated':False,'display_blocker':'Existing sandbox /bin/ps ownership-check denial; coordinator must launch native viewer. No bypass attempted.'})
    check={'runs':len(runs),'scalars_checked':count,'hparams_runs_checked':len(expected_hp),'mismatches':mismatch,
           'actual_event_loading':True,'dashboard_display_verified':False}
    d.save(out/'tensorboard_verification.json',check)
    print(json.dumps(check),flush=True)
    if mismatch: raise ValueError('TensorBoard reload mismatch')


if __name__=='__main__': main()
