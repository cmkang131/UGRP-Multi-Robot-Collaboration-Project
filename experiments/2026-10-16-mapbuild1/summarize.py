"""Run on gcp2 CPU: verify raw hashes and make a small delivery, no model/physics."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text())
def write(path,value):path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    verified=[];mismatches=[]
    roots=['capture-r2/frames','replay-r3','candidate-fast7','candidate-orange-columns-fast7']
    for root in roots:
        folder=a.raw/root;manifest=read(folder/'SHA256SUMS.json')
        for name,expected in manifest.items():
            actual=digest(folder/name)
            if actual!=expected:mismatches.append(str(folder/name))
            verified.append(dict(path=str(folder/name),sha256=actual,bytes=(folder/name).stat().st_size))
    playback=read(a.raw/'playback-r1/receipts.json')
    for seq in playback['records']:
        for name,receipt in seq['files'].items():
            path=a.raw/'playback-r1'/seq['sequence']/name
            actual=digest(path)
            if actual!=receipt['sha256']:mismatches.append(str(path))
            verified.append(dict(path=str(path),sha256=actual,bytes=path.stat().st_size))
    if mismatches:raise ValueError('RAW_HASH_MISMATCH:'+repr(mismatches))
    metrics={};funnels={}
    for name in roots[1:]:
        summary=read(a.raw/name/'summary.json')
        metrics[name]=[dict(sequence=r['sequence'],method=r['method'],tracked_n=r['tracked_n'],pairs=r['pairs'],
            xy_p95_m=r['ate_xy_m']['p95'],yaw_p95_deg=r['ate_yaw_deg']['p95'],
            scale_p50=r['translation_scale_ratio']['p50'],longest_tracked_pairs=r['longest_tracked_pairs']) for r in summary['results']]
        funnels[name]=read(a.raw/name/'rejection-table.json')
        write(a.output/(name+'-summary.json'),summary)
    # Every failed invocation is preserved, including pre-frame initialization
    # and the source-deployment error. They are not tracking denominator rows.
    attempts=[dict(name='capture-init',exit=read(a.raw/'capture-exit.json')['exit_code'],status='HOST_ERROR',
        reason='relative texture asset path; fixed renderer cwd',log=str(a.raw/'capture.log')),
        dict(name='capture-r2',exit=read(a.raw/'capture-r2/capture-exit.json')['exit_code'],status='cap_end',
             conditions=6,frames=246,log=str(a.raw/'capture-r2/capture.log')),
        dict(name='replay-r1',exit=read(a.raw/'replay-r1-exit.json')['exit_code'],status='ANALYSIS_ERROR',
             reason='loaded camera qualification exception; now explicit unknown',log=str(a.raw/'replay-r1.log')),
        dict(name='replay-r2',exit=read(a.raw/'replay-r2-exit.json')['exit_code'],status='HOST_ERROR',
             reason='analysis launched before source checkout completed; rerun after SHA verification',log=str(a.raw/'replay-r2.log')),
        dict(name='replay-r3',exit=read(a.raw/'replay-r3-exit.json')['exit_code'],status='COMPLETE')]
    attempts += [dict(name='candidate-'+r['candidate'],exit=r['exit_code'],status='COMPLETE' if r['exit_code']==0 else 'ANALYSIS_ERROR') for r in read(a.raw/'candidates-exit.json')]
    attempts.append(dict(name='playback',exit=read(a.raw/'playback-command.json')['exit_code'],status='COMPLETE'))
    labels=read(a.raw/'capture-r2/frames/eval-only.json')
    summary=dict(schema='ugrp.mapbuild1.summary.v1',status='NOT_READY',scope='kinematic MJWarp RGB feasibility; physics0',
        host_analysis=platform.node(),host_render='ugrp-act-l4-gcp2',project='ugrp-sim-b-1014',shared_load=True,
        scene='walls_floor_contrast_v5_indigo110_s80',floor='floor_light_textured_v1',quality='no_mip_v1',
        renderer_source_sha='3c598b816b823ef93d064b2f30ffd07cf5493816',capture_source_sha='24c515f43d1aa919caa06387e4fdfec0fa3dce28',
        baseline_source_sha='01c46bf2ab9d570ef478093bc36f1bcb23be85a1',candidate_source_sha='fe77e1a791eda8fb3209a58aa9643a7ed71819fa',
        map=labels['map'],map_sha256=labels['map_sha256'],map_coverage='1 authored map; one fixture origin; not full-map coverage',
        recorded=dict(conditions_n=6,conditions_N=6,frames_n=246,frames_N=246,pairs=240,sim_s_per_sequence=4,hz=10),
        camera_qualified=dict(conditions_n=3,conditions_N=6,frames_n=123,frames_N=246,pairs_n=120,pairs_N=240),
        results=metrics,attempts=attempts,verified_files=len(verified),hash_mismatches=mismatches,
        raw=str(a.raw),physical_driving_runs=0,occupancy_maps_from_exploration=0,transport_runs=0,model_calls=0,
        stages=dict(survey='COMPLETE_REFERENCES_ONLY',feasibility='PARTIAL_NOT_ADMITTED',mapping='NOT_STARTED',map_transport='NOT_STARTED'),
        remaining=['HIGH command camera model unqualified; no truth bypass',
            'ORB map correspondence loss persists',
            'actual MJWarp issued-command driving and command/ultrasonic scale not measured',
            'frozen warp5 renderer full semantic gate not admitted; no control qualification inferred',
            'exploration occupancy geometry/coverage and same-seed warp7 transport not measured',
            'ORB-SLAM3 and learned L4 models surveyed but not executed'],
        inference='RGB column masking substantially improves LK on these cases; no independent holdout or sole-cause claim')
    write(a.output/'summary.json',summary)
    write(a.output/'rejection-table.json',dict(schema='ugrp.mapbuild1.funnel.v1',scope='pair-level; distinct candidates, no pooled counts',
        tables=funnels,raw=str(a.raw),reproduction=['python3',__file__,*__import__('sys').argv[1:]]))
    write(a.output/'next-queue.json',dict(status='WITHHELD',enabled=False,runs=[],
        rejection_table=str(a.output/'rejection-table.json'),remaining=summary['remaining']))
    write(a.output/'artifact-receipts.json',dict(verified_files=len(verified),mismatches=mismatches,raw_bytes=sum(r['bytes'] for r in verified),
        raw_manifest_sha256={str(a.raw/root/'SHA256SUMS.json'):digest(a.raw/root/'SHA256SUMS.json') for root in roots},
        own_manifest_sha256=digest(a.raw/'capture-r2/frames/own.json'),
        playback_receipts_sha256=digest(a.raw/'playback-r1/receipts.json')))
    write(a.output/'attempts.json',attempts)
    write(a.output/'host-lifecycle.json',dict(cpu=read(a.raw/'cpu-final-leases.json'),
        l4=read(a.raw/'capture-r2/lease-release.json'),vm_stop_attempted=False))
    for src,dst in [('capture-r2/frames/summary.json','capture-summary.json'),
                    ('capture-r2/capture-queue.json','capture-queue.json'),('candidates-queue.json','candidates-queue.json'),
                    ('playback-r1/receipts.json','playback-receipts.json')]:
        (a.output/dst).write_bytes((a.raw/src).read_bytes())
    write(a.output/'SHA256SUMS.json',{p.name:digest(p) for p in a.output.iterdir() if p.is_file()})
    print(json.dumps(dict(status=summary['status'],verified_files=len(verified),mismatches=mismatches)))


if __name__=='__main__':main()
