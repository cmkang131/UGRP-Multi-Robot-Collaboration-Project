"""Frozen post-run raw contact/state evaluation and saved-RGB delivery only."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
from pathlib import Path
import platform
import shutil
import subprocess

from scripts.run_s3_synchronized_carry_cohort import PLAN


def read(path):
    return json.loads(path.read_text())


def rows(path):
    return [json.loads(s) for s in path.read_text().splitlines()]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def events(value):
    if isinstance(value, dict):
        if value.get('event') in ('coarse_fine','coarse_fine_aligned'):
            yield value
        else:
            for child in value.values():
                yield from events(child)
    elif isinstance(value, list):
        for child in value:
            yield from events(child)


def sustained(times, minimum=.20):
    start = previous = None
    for t in sorted(set(times)):
        if previous is None or t-previous>.051:
            start=t
        if t-start>=minimum-1e-7:
            return start
        previous=t
    return None


def summarize(raw):
    manifest=read(raw/'artifacts.sha256.json')
    for rel, expected in manifest.items():
        if sha(raw/rel)!=expected:
            raise ValueError('raw hash mismatch: '+rel)
    b=read(raw/'bundle.json');r=read(raw/'result.json');states=read(raw/'stage-states.json')
    ev=list({json.dumps(e,sort_keys=True):e for e in events(read(raw/'student_record.json'))}.values())
    truth={round(x['t'],6):x['items'] for x in rows(raw/'eval_only/referee_truth.jsonl')}
    contacts=rows(raw/'eval_only/contacts.jsonl')
    robots=('r1','r2') if b['case']=='pair' else ('r3',)
    item='beam_1' if b['case']=='pair' else 'cyan_1'
    result=dict(source_sha=b['source_sha'],host='oracle-x86',case=b['case'],condition=b['initial_condition'],
        seed=b['seed'],status=r['status'],failure=r.get('failure'),physical_stop=r.get('physical_stop'),
        wall_s=r['wall_s'],sim_s=r.get('check_sim_s',0),robots={},model_calls=0,
        artifact_verification=dict(files=len(manifest),all_hashes_match=True),
        host_timing=read(raw/'host-timing.json'),scope='DEV stage regression; not E2E or confirmation')
    physical={rid:dict(grasp=[],lift=[],carry_points=[]) for rid in robots}
    for rid in robots:
        rr=[x for x in states if rid in x['robots']]
        first=lambda predicate:next((x['t'] for x in rr if predicate(x['robots'][rid])),None)
        align=next((e.get('sim_s',e.get('t')) for e in ev if e['robot_id']==rid and e['event']=='coarse_fine_aligned'),None)
        cmds=rows(raw/f'robots/{rid}/commands.jsonl')
        signs=[math.copysign(1,c['turn']) for c in cmds if c.get('kind') in ('drive','mecanum') and c.get('turn')]
        result['robots'][rid]=dict(alignment=align,
            hover=first(lambda x:x['state']=='hover' or x.get('blind_phase')=='hover' and x['state']=='pregrasp_descend'),
            descent=first(lambda x:x['state']=='blind_descent' or x.get('blind_phase')=='descend' and x['state']=='pregrasp_descend'),
            close=first(lambda x:x['state']=='grasp'),lift_entry=first(lambda x:x['state'] in ('lift','low_lift','raise_high')),
            carry_entry=first(lambda x:x['state']=='carry'),turn_reversals=sum(a!=b for a,b in zip(signs,signs[1:])),
            commands=len(cmds),fine_pan_commands=sum(e.get('phase')=='pan' for e in ev if e['robot_id']==rid))
    for x in contacts:
        t=x['t'];cargo=truth.get(round(t,6),{}).get(item)
        if cargo is None:continue
        touched={c[k] for c in x['contacts'] if 'cargo_'+item in c['geom1'] or 'cargo_'+item in c['geom2'] for k in ('geom1','geom2')}
        both={rid:all(rid+'__'+side+'_finger' in touched for side in ('left','right')) for rid in robots}
        for rid in robots:
            rr=result['robots'][rid]
            if rr['close'] is not None and t>=rr['close'] and both[rid]:
                physical[rid]['grasp'].append(t)
            if cargo['z']>.06 and all(both.values()):
                physical[rid]['lift'].append(t)
                if rr['carry_entry'] is not None and t>=rr['carry_entry']:
                    physical[rid]['carry_points'].append((t,cargo['x'],cargo['y']))
    for rid in robots:
        rr=result['robots'][rid];p=physical[rid]
        pts=p['carry_points'];movement=max((math.dist(v[1:],pts[0][1:]) for v in pts),default=0.)
        rr.update(grasp=sustained(p['grasp']),lift=sustained(p['lift']),carry_xy_m=movement,
            carry=bool(rr['carry_entry'] is not None and sustained(p['lift']) is not None and movement>=.02),
            contact_lift_samples=len(p['lift']),max_cargo_z_m=max(v[item]['z'] for v in truth.values()))
    result['joint']={k:all(result['robots'][rid][k] is not None if k!='carry' else result['robots'][rid][k] for rid in robots)
                     for k in ('alignment','grasp','lift','carry')}
    from scripts.diagnose_s3_endpoint_visibility import events as beam_events
    def walk(x):
        if isinstance(x,dict):
            if 'event' in x:yield x
            else:
                for v in x.values():yield from walk(v)
        elif isinstance(x,list):
            for v in x:yield from walk(v)
    all_events=list({json.dumps(e,sort_keys=True):e for e in walk(read(raw/'student_record.json'))}.values())
    for rid,rr in result['robots'].items():
        ee=[e for e in all_events if e.get('robot_id')==rid]
        rr['restore_collisions']=sum(e['event']=='align_posture_restore' for e in ee)
        rr['last_visible_uses']=sum(e['event']=='last_visible_approach' for e in ee)
        rr['endpoint_rejected_frames']=sum(e['event']=='beam_obs' and not e.get('end_visible',False) for e in ee)
        rr['endpoint_stall']=rr['alignment'] is None and rr['endpoint_rejected_frames']>0
    result['commands']=sum(v['commands'] for v in result['robots'].values())
    target=.1518 if b['case']=='pair' else .1
    result['target_distance_m']=target
    result['joint']['target_distance']=all(v['carry'] and v['carry_xy_m']>=target for v in result['robots'].values())
    result['robot_max_tilt_deg']={rid:max(x['tilt_deg'] for x in rows(raw/f'eval_only/{rid}/trajectory.jsonl')) for rid in robots}
    dynamics=rows(raw/'eval_only/cooperative-dynamics.jsonl') if (raw/'eval_only/cooperative-dynamics.jsonl').exists() else []
    result['cargo_max_tilt_deg']=max((x['cargo_tilt_deg'] for x in dynamics),default=None)
    reason=(result.get('physical_stop') or result.get('failure') or '')
    result['tilt_aborts']=int('TILT' in reason);result['drop_aborts']=int('DROP' in reason or 'GRIP_LOST' in reason)
    result['final_controller_states']=r.get('final')
    result['force_scope']='evaluation only; exact contact forces stored in raw, never controller input'
    result['contact_forces_n']={rid:dict(max_normal_sum=max((x['robots'][rid]['normal_sum_n'] for x in dynamics),default=None),
        max_resultant=max((math.sqrt(sum(v*v for v in x['robots'][rid]['force_world_n'])) for x in dynamics),default=None)) for rid in ('r1','r2')}
    return result


def video(raw,out):
    import cv2
    import numpy as np
    frames=[rows(raw/f'robots/{r}/frames.jsonl')[::4] for r in ('r1','r2','r3')]
    if len({len(f) for f in frames})!=1:raise ValueError('unsynchronized saved RGB')
    if not frames[0]:return None
    path=out/'execution.mp4'
    proc=subprocess.Popen([shutil.which('ffmpeg'),'-v','error','-f','rawvideo','-pixel_format','bgr24',
        '-video_size','1920x480','-framerate','20','-i','-','-an','-c:v','libx264','-threads','1',
        '-preset','veryfast','-crf','28','-pix_fmt','yuv420p','-movflags','+faststart',str(path)],stdin=subprocess.PIPE)
    try:
        for triple in zip(*frames):
            imgs=[]
            for rid,frame in zip(('r1','r2','r3'),triple):
                img=cv2.imread(str(raw/frame['path']))
                if img is None:raise ValueError('missing saved RGB')
                cv2.putText(img,f'{rid} | s3fix17 | SIM {frame["sim_time"]:.2f} | 4x',
                    (8,25),cv2.FONT_HERSHEY_SIMPLEX,.55,(255,255,255),1)
                imgs.append(img)
            proc.stdin.write(np.hstack(imgs).tobytes())
    finally:proc.stdin.close()
    if proc.wait()!=0:raise RuntimeError('ffmpeg failed')
    cap=cv2.VideoCapture(str(path));ok,_=cap.read();n=int(cap.get(cv2.CAP_PROP_FRAME_COUNT));fps=cap.get(cv2.CAP_PROP_FPS);cap.release()
    if not ok or n!=len(frames[0]) or fps!=20.:raise ValueError('video decode mismatch')
    return dict(path=str(path),sha256=sha(path),frames=n,fps=fps,duration_s=n/fps,playback=4)


def evaluate(raw,out):
    out.mkdir(parents=True,exist_ok=False)
    result=summarize(raw);report=out/'report.json';report.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    v=video(raw,out)
    scalars={'offline/'+k:int(vv) for k,vv in result['joint'].items()}
    scalars.update({'offline/n':1,'offline/host_errors':int(result['status']=='HOST_ERROR'), 'offline/tilt_aborts':result['tilt_aborts'],'offline/drop_aborts':result['drop_aborts']})
    for rid,r in result['robots'].items():
        for k in ('alignment','grasp','lift','carry'):
            scalars[f'offline/{rid}/{k}']=int(r[k] is not None if k!='carry' else r[k])
        for k in ('turn_reversals','carry_xy_m','contact_lift_samples'):
            scalars[f'offline/{rid}/{k}']=r[k]
    value=dict(schema='ugrp.s3_coarse_fine_delivery.v1',derived_view_only=True,host='oracle-x86',
        source_sha=result['source_sha'],case=raw.parent.name,seed=result['seed'],policy='synchronized_pulses_v1',clock='SIM',
        status=result['status'],wall_s=result['wall_s'],sim_s=result['sim_s'],commands=result['commands'],model_calls=0,
        offline_source=dict(path=str(report.resolve()),sha256=sha(report)),
        offline_scalar_scope=result['scope'],offline_scalars=scalars,video=v,
        hparam_metrics=['offline/alignment','offline/grasp','offline/lift','offline/carry','result/wall_s','result/commands','result/model_calls'])
    (out/'result.json').write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
    return dict(name=raw.parent.name,**result,report_sha256=sha(report),video=v)


def main():
    p=argparse.ArgumentParser();p.add_argument('--cohort',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if platform.system()!='Linux' or platform.machine()!='x86_64':raise ValueError('Oracle x86 evaluation only')
    plan=read(PLAN)
    for r in plan['runs']:
        if not (a.cohort/r['name']/'EXIT').exists():raise ValueError('entire batch must finish first')
    a.output.mkdir(parents=True,exist_ok=False)
    with ThreadPoolExecutor(max_workers=10) as pool:
        results=list(pool.map(lambda r:evaluate(a.cohort/r['name']/'raw',a.output/r['name']),plan['runs']))
    summary=dict(runs=results,n=len(results),counts={k:sum(r['joint'][k] for r in results) for k in ('alignment','grasp','lift','carry','target_distance')})
    (a.output/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(n=summary['n'],counts=summary['counts'])))


if __name__=='__main__':main()
