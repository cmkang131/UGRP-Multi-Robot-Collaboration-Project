"""Finite gcp2 CPU replay, map scoring and headless playback of clean MJWarp RGB."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x):p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('input','vision-source','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--execute',action='store_true');a=p.parse_args()
    if not a.execute or platform.system()!='Linux' or not platform.node().startswith('ugrp-sim-gcp2'):
        p.error('explicit gcp2 CPU analysis only')
    capture=read(a.input/'summary.json')
    if capture['status']!='cap_end':raise ValueError('COMPLETE_CAPTURE_REQUIRED')
    a.output.mkdir(parents=True,exist_ok=False)
    env={**os.environ,'PYTHONPATH':str(ROOT),'MUJOCO_GL':'osmesa','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'}
    commands=[]
    def call(cmd,*,vision=False):
        cmd=list(map(str,cmd));commands.append(cmd)
        with (a.output/'analysis.log').open('a') as log:
            subprocess.run(cmd,cwd=a.vision_source if vision else ROOT,
                env={**env,'PYTHONPATH':str(a.vision_source)+':'+str(ROOT)} if vision else env,
                stdout=log,stderr=subprocess.STDOUT,check=True)
    py=sys.executable;trajectories={}
    prior=a.input/'rejection-table.json'
    for candidate in ('legacy','orange-columns-fast7'):
        out=a.output/candidate
        write(a.output/(candidate+'-queue.json'),dict(rejection_table=str(prior.resolve()),input=str(a.input),candidate=candidate))
        call([py,'-m','scripts.mapbuild1_replay','--mapbuild1-v1','--candidate',candidate,'--input',a.input,
              '--evaluation-labels',a.input/'eval-only.json','--output',out])
        trajectories[candidate]=read(out/'trajectory.json')
    # Command-only trajectory is derived from issued history; no label input.
    sys.path.insert(0,str(ROOT))
    import numpy as np
    from harness.e2e_rgb_vo import between,compose
    from scripts.mapbuild1_replay import score
    manifest=read(a.input/'own.json');poses={};cmd=[]
    for frame in manifest['frames']:
        name=frame['sequence'];poses.setdefault(name,np.zeros(3));poses[name]=compose(poses[name],frame['command_delta'])
        cmd.append(dict(sequence=name,frame_id=frame['frame_id'],lk_pose=poses[name].tolist()))
    write(a.output/'command-trajectory.json',cmd);trajectories['command']=cmd
    # Causal trajectories are persisted before opening actual state labels.
    labels=read(a.input/'eval-only.json');truth={(r['sequence'],r['frame_id']):r['pose'] for r in labels['frames']}
    origins={name:labels['first_origin'][i] for i,name in enumerate(dict.fromkeys(r['sequence'] for r in manifest['frames']))}
    phases=[]
    for name in origins:
        for start,end,axis in ((0,10,'settle'),(10,20,'forward'),(20,30,'left'),(30,40,'turn')):
            actual=between(truth[name,start],truth[name,end]);methods={}
            for method,rows in trajectories.items():
                values={r['frame_id']:r['lk_pose'] for r in rows if r['sequence']==name}
                delta=between(values[start],values[end]);denom=actual[2] if axis=='turn' else np.linalg.norm(actual[:2])
                numerator=delta[2] if axis=='turn' else np.linalg.norm(delta[:2])
                methods[method]=dict(delta=delta.tolist(),predicted_over_actual=float(numerator/denom) if denom else None)
            phases.append(dict(sequence=name,axis=axis,sim_range=[start/10,end/10],actual_delta=actual.tolist(),methods=methods))
    write(a.output/'command-phase-scale.json',phases)
    metrics={candidate:score(rows,labels) for candidate,rows in trajectories.items() if candidate!='command'}
    write(a.output/'tracking-scores.json',metrics)
    from collections import Counter
    tracking_funnels=[]
    for candidate,rows in trajectories.items():
        if candidate=='command':continue
        pairs=[r for r in rows if r['frame_id']!=0]
        qualified=[r for r in pairs if not r['lk']['status'].startswith('unknown_camera')]
        measured=[r for r in qualified if r['lk']['status']=='measured']
        tracking_funnels.append(dict(candidate=candidate,unit='adjacent_pair',stages=[
            dict(stage='input_pairs',cumulative_pass_n=len(pairs),rejected_n=0),
            dict(stage='qualified_camera',cumulative_pass_n=len(qualified),rejected_n=len(pairs)-len(qualified)),
            dict(stage='measured_LK',cumulative_pass_n=len(measured),rejected_n=len(qualified)-len(measured))],
            reasons=dict(Counter(r['lk']['status'] for r in pairs if r['lk']['status']!='measured')),
            rejection_fields='trajectory: category/reason/blocked_object/minimum_gap_m/gap_status'))
    maps={};map_tables={}
    for candidate in ('legacy','orange-columns-fast7'):
        out=a.output/(candidate+'-maps');prior=a.output/candidate/'rejection-table.json'
        write(a.output/(candidate+'-maps-queue.json'),dict(rejection_table=str(prior.resolve()),diagnostic_only=True))
        call([py,ROOT/'scripts/mapbuild2_map.py','--execute','--input',a.input,'--trajectory',a.output/candidate/'trajectory.json',
              '--vision-source',a.vision_source,'--output',out])
        map_tables[candidate]=read(out/'rejection-table.json')
        for prediction in sorted(out.glob('*-predicted.json')):
            name=prediction.name.removesuffix('-predicted.json');target=prediction.with_name(name+'-score.json')
            call([py,'-m','scripts.mapbuild2_map_eval','--predicted',prediction,'--static-map',
                a.vision_source/'maps/zones_final_v3/zone_hardmaps1_h1_final_v3.json','--origin',*origins[name],'--output',target])
            maps[candidate+'/'+name]=read(target)
    write(a.output/'map-scores.json',maps)
    call([py,ROOT/'scripts/mapbuild2_camera_eval.py','--input',a.input,'--vision-source',a.vision_source,
          '--output',a.output/'camera-eval.json'],vision=True)
    # Every camera is recorded by the MJWarp renderer; composing files here is
    # evaluation only. Explicit exact frame count avoids duplicate tail padding.
    playback=a.output/'playback';playback.mkdir();receipts=[]
    for case in origins:
        folder=playback/case;folder.mkdir();ins=[]
        for camera in ('overview','r1','r2'):ins+=['-framerate','30','-i',str(a.input/case/(camera+'-%04d.jpg'))]
        video=folder/'review-3x.mp4'
        call(['ffmpeg','-nostdin','-loglevel','error',*ins,'-filter_complex','[0:v][1:v][2:v]hstack=inputs=3[v]',
              '-map','[v]','-frames:v','41','-fps_mode','vfr','-an','-c:v','libx264','-crf','28','-pix_fmt','yuv420p','-threads','1',video])
        for camera in ('overview','r1','r2'):
            for name,filter_ in [('whole-2hz',r'select=not(mod(n\,5)),scale=320:240,tile=3x3'),
                                  ('terminal-10hz','scale=320:240,tile=7x6')]:
                call(['ffmpeg','-nostdin','-loglevel','error','-framerate','10','-i',a.input/case/(camera+'-%04d.jpg'),
                      '-vf',filter_,'-frames:v','1','-threads','1',folder/(camera+'-'+name+'.jpg')])
        probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(video)]))
        if video.stat().st_size>8*1024**2:raise ValueError('VIDEO_8MIB_LIMIT')
        receipts.append(dict(case=case,sim_range=[0,4],video_probe=probe,files={p.name:dict(bytes=p.stat().st_size,sha256=sha(p)) for p in folder.iterdir()}))
    write(playback/'receipts.json',receipts)
    write(a.output/'reproduce.json',commands)
    write(a.output/'rejection_table.json',dict(raw=str(a.input),reproduction=commands,
        lk_tracking=tracking_funnels,tracking={k:read(a.output/k/'rejection-table.json') for k in ('legacy','orange-columns-fast7')},mapping=map_tables,
        gate4=dict(status='WITHHELD',reason='warp10 final NOT_READY; repeated CPU contact export HOST_ERROR before30SIM; no same-seed qualified arrival reference',
                   blocked_object='warp10:CPU_contact_export',minimum_gap_m=None,gap_status='not_measured')))
    write(a.output/'summary.json',dict(status='ANALYZED_NOT_ADMITTED',capture=capture,tracking=metrics,
        map_scores=maps,input_audit=dict(top_actor_reads=0,truth_feedback=0,cpu_physics_steps=0),
        scope='one clean shared start,4SIMs; HIGH unloaded/closed remains unqualified; no frontier or arrival success'))
    write(a.output/'SHA256SUMS.json',{str(p.relative_to(a.output)):sha(p) for p in a.output.rglob('*') if p.is_file()})


if __name__=='__main__':main()
