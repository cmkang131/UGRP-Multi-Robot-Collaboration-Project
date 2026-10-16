"""Post-seal reporting only; no estimator, renderer or simulator imports."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import socket
import subprocess


def read(path):
    return json.loads(path.read_text() if path.exists() else
                      subprocess.check_output(['zstd','-qdc',str(path)+'.zst'],text=True))


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path,value):path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--corrections',type=Path,required=True)
    a=p.parse_args()
    assert socket.gethostname().split('.')[0]=='ugrp-act-l4-gcp3'
    d=read(a.input/'probe-lk.json');rows=[];error_rows=[]
    for world in d['worlds']:
        raw=a.run/f"world-{world['world']:03d}/raw";old=read(raw/'result.json')
        for rid,robot in world['robots'].items():
            rr=robot['rows'];cols=Counter();zones=Counter()
            for r in rr:cols.update(r['column_reasons']);zones.update(r['zone_colour_components_auxiliary'])
            rows.append(dict(world=world['world'],seed=world['seed'],robot=rid,views=len(rr),
                camera_qualified=sum(r['camera_qualified'] for r in rr),wall_views=sum(r['wall_hit_columns']>0 for r in rr),
                wall_columns=sum(r['wall_hit_columns'] for r in rr),floor_views=sum((r['floor_features'] or 0)>0 for r in rr),
                floor_features=sum((r['floor_features'] or 0) for r in rr),
                zone_colour_components_auxiliary=dict(zones),column_reasons=dict(cols),
                t_range=[rr[0]['t'],rr[-1]['t']],map_error_xy_m=None,map_error_yaw_deg=None,
                map_error_status='unmeasured_owner_static_map_api_pending',
                lk_motion_counts=dict(Counter(r['lk']['status'] for r in rr))))
            ev=old['lookaround_result'][rid]['evaluation']
            # Previously recorded errors are reference columns, never new-path
            # correction scores. No frame alignment is fitted on evaluation.
            error_rows.append(dict(world=world['world'],rid=rid,
                old_before=ev.get('before'),old_after=ev.get('after'),
                new_before=None,new_after=None,new_map_error_status='unmeasured_owner_static_map_api_pending',
                verification='truth stored for evaluator only; estimator prediction seal has no truth inputs'))
    flat=[r for w in d['worlds'] for robot in w['robots'].values() for r in robot['rows']]
    f0=flat;f1=[r for r in f0 if r['camera_qualified']]
    f2=[r for r in f1 if (r['floor_features'] or 0)>0]
    f3=[r for r in f2 if r['wall_hit_columns']>0]
    previous=len(f0);stages=[]
    for name,items in [('own_rendered_views',f0),('qualified_FK',f1),('floor_features_present',f2),('wall_hits_present',f3),('static_map_acquired',[])]:
        stages.append(dict(stage=name,cumulative_pass_n=len(items),rejected_n=previous-len(items)));previous=len(items)
    dump(a.input/'detection-table.json',dict(rows=rows,scope='open-gripper sparse views only; presence is not localization qualification'))
    dump(a.input/'error-table.json',dict(rows=error_rows,new_pose_errors_measured=False,
        reason='owner static map acquisition API not available; no evaluator pose was used as initialization'))
    funnel=dict(raw=str(a.input),source_run=str(a.run),reproduction=['summarize_selfmap_inputs.py','--input',str(a.input),'--run',str(a.run),'--corrections',str(a.corrections)],
        stages=stages,reasons=[dict(category='owner_api_pending',reason='static_map_acquisition_api_unavailable',
            count=len(f3),blocking_object='static_map_wall_acquisition',minimum_gap_m=None,gap_status='not_measured')],
        reason_counts=d['column_reasons'],
        interpretation='Sequential availability audit only. Floor features and wall hits do not establish matching acceptance. Auxiliary zone signatures are parallel counts.')
    dump(a.input/'rejection_table.json',funnel)
    correction=read(a.corrections);verified=[]
    for row in correction['files']:
        file=Path(row['path']);assert file.is_file() and file.stat().st_size==row['bytes'] and sha(file)==row['sha256']
        verified.append(str(file))
    dump(a.input/'metadata-corrections-verification.json',dict(verified_files=len(verified),all_SHA_equal=True,
        original_files_overwritten=0,duplicate_corrections_created=0,correction_index_sha256=sha(a.corrections)))
    short={k:v for k,v in d.items() if k!='worlds'}
    short.update(detection_table='detection-table.json',error_table='error-table.json',rejection_table=str(a.input/'rejection_table.json'),
        gate_ready=False,release_A40_submitted=False,release_B40_submitted=False,
        map_error_status='unmeasured_owner_static_map_api_pending',metadata_corrections_verified=len(verified),
        report_scope='component diagnostic; not a completed new-path localization gate')
    dump(a.input/'summary.json',short)
    md=['|세계|seed|로봇|뷰|벽 검출뷰/열|바닥 특징뷰/특징|구역 색 성분(보조)|새 지도 오차|',
        '|---:|---:|---|---:|---|---|---|---|']
    for r in rows:
        md.append(f"|{r['world']}|{r['seed']}|{r['robot']}|{r['views']}|{r['wall_views']}/{r['wall_columns']}|{r['floor_views']}/{r['floor_features']}|{r['zone_colour_components_auxiliary']}|미측정(API 대기)|")
    (a.input/'detection-table.md').write_text('\n'.join(md)+'\n')
    print(json.dumps(short))


if __name__=='__main__':main()
