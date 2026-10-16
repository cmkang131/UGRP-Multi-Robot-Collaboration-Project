"""Saved-ledger calibration/evaluation only; no simulator imports or execution.

Fit one zero-intercept yaw gain on ACT8 pure in-place command intervals.
Freeze it before replaying ACT9 and ACT10. Truth never enters CommandSearch.
"""
import argparse
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import subprocess

import numpy as np

from harness.grasp_act_data import read_json, read_rows, sha256, write_json
from harness.grasp_act_search import CommandSearch, command_delta
from scripts.audit_grasp_act_act10 import adapter_replay, angle_error
from harness.grasp_act_dart import recovery_hooks
from scripts.run_grasp_act_recovery import CALIBRATION_MODE
from scripts.grasp_act_training_guard import ROOT

RECORD=ROOT/'experiments/2026-10-15-act-train'
ELIGIBLE=('start','fold','approach','align','relook')


def path_for(root, relative):
    p=root/relative
    return p if p.exists() else Path(str(p)+'.zst')


def load(root):
    paths={k:path_for(root,v) for k,v in {
        'commands':'recovery-commands.jsonl','base':'recovery-eval-only.jsonl',
        'teacher':'raw/teacher-commands.jsonl','cargo':'raw/eval-only.jsonl',
        'result':'raw/result.json'}.items()}
    rows={k:read_rows(p) for k,p in paths.items() if k!='result'}
    # Extra lookaround evaluation events are not command-boundary cargo rows.
    rows['cargo']=[r for r in rows['cargo'] if 'cargo_xyz' in r]
    lengths={k:len(v) for k,v in rows.items()}
    n=min(lengths.values())
    if not n:raise ValueError('empty ledger')
    for i in range(n):
        if len({v[i]['t'] for v in rows.values()})!=1:
            raise ValueError('command boundary clock mismatch')
    # Partial interrupted runs remain partial; never call their result complete.
    result=read_json(paths['result']);recovery=result.get('recovery',{})
    integrity={}
    for key,expected in [('commands',recovery.get('sha256')),
                         ('base',recovery.get('evaluation_only',{}).get('sha256'))]:
        p=paths[key]
        decoded=subprocess.check_output(['zstd','-qdc',str(p)]) if p.suffix=='.zst' else p.read_bytes()
        actual=hashlib.sha256(decoded).hexdigest()
        if expected is not None and actual!=expected:raise ValueError('decoded ledger hash mismatch')
        integrity[key]={'decoded_sha256':actual,'result_hash_verified':expected is not None}
    return {k:v[:n] for k,v in rows.items()}, {
        'name':root.name,'result_status':result.get('status'),
        'physical_success':result.get('physical_success'),'integrity':integrity,
        'ticks':n,'unpaired_tail_ticks':{k:v-n for k,v in lengths.items()},
        'raw':{k:{'path':str(p),'sha256':sha256(p)} for k,p in paths.items()}}


def rotation_intervals(rows):
    values=[]
    for i,row in enumerate(rows['commands'][:-1]):
        dt=rows['commands'][i+1]['t']-row['t']
        if not 0<dt<=.15+1e-8:raise ValueError('invalid command interval')
        dx,dy,yaw=command_delta(row['applied_command'],dt)
        if row['phase_before'] not in ELIGIBLE or abs(dx)>1e-10 or abs(dy)>1e-10 or abs(yaw)<1e-6:
            continue
        a=rows['base'][i]['base_rpy'][2]; b=rows['base'][i+1]['base_rpy'][2]
        actual=math.atan2(math.sin(b-a),math.cos(b-a))
        values.append({'t':row['t'],'nominal_rad':yaw,'actual_rad':actual,
            'pulse_s':row['applied_command']['duration_s'][0],
            'probe':row.get('perturbation_interval',False),
            'active_search':row.get('active_search') is not None})
    return values


def fit_gain(intervals):
    if len(intervals)<2:raise ValueError('insufficient pure rotation calibration')
    x=np.array([r['nominal_rad'] for r in intervals]); y=np.array([r['actual_rad'] for r in intervals])
    gain=float(x@y/(x@x))
    if not .1<=gain<=2.:raise ValueError('invalid fitted yaw gain')
    return gain


def summary(values):
    return {'N':len(values),**({'median_deg':float(np.median(values)),
        'p95_deg':float(np.percentile(values,95)),'max_deg':float(max(values))} if values else {})}


def predictions(rows, gain):
    search=CommandSearch(yaw_gain=gain); previous=None; result=[]
    for row,teacher in zip(rows['commands'],rows['teacher']):
        eligible=row['phase_before'] in ELIGIBLE
        search.observe(row['t'],teacher['visible_target'],previous,holding=not eligible,eligible=eligible)
        result.append(deepcopy(search.point))
        previous=row['applied_command']
    return result


def evaluate(rows, gain):
    # Complete both controller passes BEFORE exposing evaluator truth.
    estimates={key:predictions(rows,g) for key,g in [('off',1.),('on',gain)]}
    errors={key:[] for key in estimates}; trace=[]
    for i,row in enumerate(rows['commands']):
        if rows['teacher'][i]['visible_target'] is not None or estimates['off'][i] is None:continue
        values={k:angle_error(p[i],rows['base'][i],rows['cargo'][i]['cargo_xyz']) for k,p in estimates.items()}
        for k,v in values.items():errors[k].append(v)
        trace.append({'t':row['t'],**values})
    return {k:summary(v) for k,v in errors.items()}, trace


def audit(runs_root, output):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    cohorts={};excluded=[]
    for cohort in ('act8','act9','act10'):
        cohorts[cohort]=[]
        for root in sorted(Path(runs_root).glob(cohort+'-gate-*')):
            try:rows,entry=load(root)
            except (OSError,ValueError) as error:
                excluded.append({'name':root.name,'reason':str(error)});continue
            cohorts[cohort].append((rows,entry))
    fit_intervals=[r for rows,_ in cohorts['act8'] for r in rotation_intervals(rows)]
    gain=fit_gain(fit_intervals)  # ACT9/10 never participate in this fit.
    calibration={'mode':CALIBRATION_MODE,'yaw_gain':gain,'fit_cohort':'act8',
        'validation_cohorts':['act9','act10'],'fit_N':len(fit_intervals),
        'estimator':'zero-intercept least squares: sum(nominal*actual)/sum(nominal^2)',
        'scope':'n4-highcpu-64 saved no-load near-cargo intervals; not measured odometry online'}
    pooled={};entries=[];reference={'off':[],'on':[]}
    for cohort,runs in cohorts.items():
        all_errors={'off':[],'on':[]}
        for rows,entry in runs:
            bearing,trace=evaluate(rows,gain)
            intervals=rotation_intervals(rows)
            path=output/(entry['name']+'-evaluation.jsonl')
            path.write_text(''.join(json.dumps(v,allow_nan=False)+'\n' for v in trace))
            entry.update(cohort=cohort,bearing=bearing,rotation={
                'N':len(intervals),'observed_slope':fit_gain(intervals) if len(intervals)>=2 else None,
                'actual_abs_deg':sum(abs(math.degrees(v['actual_rad'])) for v in intervals),
                'nominal_abs_deg':sum(abs(math.degrees(v['nominal_rad'])) for v in intervals),
                'calibrated_abs_deg':gain*sum(abs(math.degrees(v['nominal_rad'])) for v in intervals),
                'probe_N':sum(v['probe'] for v in intervals),'search_N':sum(v['active_search'] for v in intervals)},
                trace={'path':str(path),'sha256':sha256(path)})
            for key in all_errors:all_errors[key].extend(v[key] for v in trace)
            if cohort=='act9' and 8316900<=int(entry['name'].split('-')[2])<=8316914:
                for key in reference:reference[key].extend(v[key] for v in trace)
            entries.append(entry)
        pooled[cohort]={k:summary(v) for k,v in all_errors.items()}
    # Search OFF regression: saved clean decisions, no physical counterfactual.
    old_source=subprocess.check_output(['git','show','567dc120:harness/grasp_act_dart.py'],cwd=ROOT,text=True)
    namespace={};exec(compile(old_source,'act10-adapter','exec'),namespace)
    model=read_json(RECORD/'act9-noise.json');regression=[]
    for seed,wanted in [(8316900,507),(8316901,487),(8316902,607)]:
        rows=next(r for r,e in cohorts['act9'] if str(seed) in e['name'])['commands']
        old,old_text=adapter_replay(rows,namespace['recovery_hooks'],model,seed)
        new,new_text=adapter_replay(rows,recovery_hooks,model,seed)
        if len(rows)!=wanted or old!=new or old_text!=new_text or new!=[r['applied_command'] for r in rows]:
            raise ValueError('search OFF regression mismatch')
        regression.append({'seed':seed,'ticks':len(rows),'commands_equal':True,'ledger_equal':True})
    report={'schema':'ugrp.act11.offline.v1','calibration':calibration,'bearing':pooled,'runs':entries,
        'act9_reference_15':{k:summary(v) for k,v in reference.items()},
        'excluded':excluded,'search_off_regression':regression,'simulation_executed':False,
        'training_rgb':False,'data_admitted':False,
        'scope':'saved observations and actual commands; bearing/yaw truth evaluation only; no new physical outcome'}
    write_json(output/'summary.json',report)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runs-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=audit(a.runs_root,a.output)
    print(json.dumps({k:r[k] for k in ('calibration','bearing','search_off_regression','excluded')},indent=2))


if __name__=='__main__':main()
