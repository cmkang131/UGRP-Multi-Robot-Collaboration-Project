"""Post-run original-file recount, including actual translated return.

Evaluation only: never imported by memory/navigation/physical runner.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import numpy as np
from scripts.egomem1_offline import read,dump,digest


def content_sha(path):
    if path.exists():return hashlib.sha256(path.read_bytes()).hexdigest()
    process=subprocess.Popen(['zstd','-dc',str(path)+'.zst'],stdout=subprocess.PIPE)
    h=hashlib.sha256()
    for chunk in iter(lambda:process.stdout.read(1024*1024),b''):h.update(chunk)
    if process.wait():raise ValueError('DECOMPRESSION_FAILED')
    return h.hexdigest()


def audit(raw, evaluation):
    checks=read(raw/'SHA256SUMS.json')
    for name,expected in checks.items():
        if content_sha(raw/name)!=expected:raise ValueError('ORIGINAL_CHANGED:'+name)
    trace=read(raw/'online-trajectory.json');truth=read(raw/'eval-only.json')['frames']
    summary=read(raw/'summary.json');base=read(evaluation/'summary.json')
    if len(trace)!=len(truth):raise ValueError('EVAL_JOIN_REQUIRED')
    for r,g in zip(trace,truth):
        if r['t']!=g['t']:raise ValueError('EVAL_TIME_JOIN_REQUIRED')
    # Start at the evaluator pose BEFORE the first actual return-forward
    # command. Rotating to face the memory alone cannot satisfy this gate.
    forward=next((i for i,r in enumerate(trace) if r['stage']=='return'
                  and r['action'][0]>0 and not r['action'][2]),None)
    return_net=(float(np.linalg.norm(np.asarray(truth[-1]['pose'][:2])-
                                    np.asarray(truth[forward]['pose'][:2]))) if forward is not None else 0.)
    diameter=summary['geometric_departure_distance_floor_m']
    translated=bool(forward is not None and return_net>=diameter)
    passed=bool(base['physical_diagnostic_pass'] and translated)
    stages=[('all_recordings',True),('original_hashes',True),
            ('visual_zone_remembered',base['creation'] is not None),
            ('actual_departure',base['departure_verified']),
            ('colour_left_camera',base['rgb_colour_absent_frames']>0),
            ('actual_return_translation',translated),
            ('qualified_same_zone_rgb',base['actual_same_zone_reacquired']),
            ('all_reacquisition_gates',passed)]
    funnel=[];left=1
    for name,ok in stages:
        keep=left*bool(ok);funnel.append(dict(stage=name,input_n=left,cumulative_pass_n=keep,rejected_n=left-keep));left=keep
    return dict(status='DEV_REACQUISITION_PASS' if passed else 'NOT_READY',
                source_sha=summary['source_sha'],original_files_sha256_verified=len(checks),
                frames=len(trace),sim_s=summary['sim_s'],wall_s=summary['wall_s'],
                first30_wall_sim=summary['first30_wall_sim'],recording_status=summary['status'],
                actual_departure_m=base['actual_departure_m'],actual_return_net_m=return_net,
                actual_return_forward_first_sim_s=truth[forward]['t'] if forward is not None else None,
                required_return_translation_m=diameter,
                acceptance_basis='same existing robot envelope diameter as departure; evaluator-only actual XY displacement, not commands or accumulated rotation wobble',
                colour_absent_frames=base['rgb_colour_absent_frames'],same_zone=base['actual_same_zone_reacquired'],
                physical_diagnostic_pass=passed,physical_delivery_success=False,student_success=False,llm_success=False,
                funnel=funnel,reason='passed_all_reacquisition_gates' if passed else next(s['stage'] for s in funnel if s['rejected_n']),
                blocked_object='not_observed',minimum_gap_m=None,gap_status='not_measured',
                raw=str(raw),evaluation=str(evaluation),reproduction=sys.argv,
                sha256=dict(original_manifest=digest(raw/'SHA256SUMS.json'),evaluation_summary=digest(evaluation/'summary.json')))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for key in ('input','evaluation','output'):p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args()
    if not platform.node().startswith('ugrp-act-l4-gcp5'):raise ValueError('GCP5_ORIGINAL_CPU_ONLY')
    dump(a.output,audit(a.input,a.evaluation))
