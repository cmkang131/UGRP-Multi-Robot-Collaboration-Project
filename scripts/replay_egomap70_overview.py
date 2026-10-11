"""Replay complete recorded r3 commands, including the inherited prefix."""
import argparse
import os
from pathlib import Path
import time
import traceback
from scripts.overview_evaluation_video import Video,Timeline,read,rows,sha,write

BASE_SHA='f26d9322c48eadbe2b28777ac1f07684ca03e124'
SEEDS={63002:False,63004:True}


def tape(raw):
    frames=rows(raw/'robots/r3/frames.jsonl');start=frames[0]['sim_time'];end=frames[-1]['sim_time']
    group={};previous=-float('inf');boot=[]
    for row in rows(raw/'robots/r3/commands.jsonl'):
        t=row['t']
        if t<previous-1e-8 or t>end+1e-8:raise ValueError('command clock is nonchronological/out of range')
        previous=t
        if row['kind']=='initial_servo_command':continue
        action={k:v for k,v in row.items() if k!='t'}
        tick=round((t-start)/.2)
        if abs(start+tick*.2-t)>1e-8:raise ValueError('command outside recorded 5Hz clock')
        if tick==0:boot.append(action)
        else:group.setdefault(tick,[]).append(action)
    return start,end,boot,group


def run(original,out,source,*,path_check=False):
    from sim.goal_route_assets import PhysicsBackend
    result=read(original/'result.json');seed=result['seed']
    if result['source_sha']!=BASE_SHA or seed not in SEEDS or original.name!=f'egomap70-{seed}-calib_traversed':
        raise ValueError('unregistered original return run')
    start,end,boot,group=tape(original)
    prefix=Path(result['checkpoint']['path']).parents[1]
    b=read(prefix/'bundle.json')
    if sha(result['checkpoint']['path'])!=result['checkpoint']['sha256']:raise ValueError('checkpoint provenance mismatch')
    own_trace=Timeline(rows(original/'own-controller.jsonl'))
    gt=rows(original/'eval_only/trajectory.jsonl');first=gt[0]
    origin=[*first['robot_xyz_m'][:2],first['robot_yaw_rad']]
    out.mkdir(parents=True,exist_ok=False)
    summary=dict(status='RUNNING',source_sha=source,original_source_sha=BASE_SHA,seed=seed,
        condition='calib_traversed',original=str(original),checkpoint=result['checkpoint'],
        prefix_source_sha=b['source_sha'],full_command_replay=True,checkpoint_state_correction=False,
        controller_run=False,model_calls=0,overlay_evaluation_only=True,return_valid=SEEDS[seed],
        start_sim_s=start,end_sim_s=end,playback_speed=8,terminal_still_s=1.5,loadavg_start=os.getloadavg())
    backend=video=None;began=time.monotonic()
    try:
        backend=PhysicsBackend(b,out,seed=seed);backend.reset(5.)
        if abs(backend.now-start)>1e-8:raise ValueError('original reset time differs')
        backend.set_deadline(end)
        for action in boot:backend.issue('r3',action)
        video=Video(backend,f'egomap70 calib_traversed seed {seed}',('r3',),
            own_trace=own_trace,origin=origin,return_valid=SEEDS[seed])
        steps=round((end-start)/.2)
        if path_check:steps=min(steps,1)
        for i in range(steps+1):
            own=backend.capture()
            if i>=10:backend.own_range()  # original sensor poll, no controller
            for action in group.get(i,[]):backend.issue('r3',action)
            backend.eval_sample()
            video.frame(backend,own)
            if i%5==0:
                write(out.parent/'health.json',dict(status='RUNNING',sim_s=backend.now,
                    wall_s=time.monotonic()-began,video_frames=video.frames,pid=os.getpid(),loadavg=os.getloadavg()))
            if i<steps:backend.advance_to(round(start+(i+1)*.2,9))
        summary['status']='PATH_CHECK' if path_check else 'COMPLETED'
    except Exception:summary.update(status='HOST_ERROR',error=traceback.format_exc())
    finally:
        for name,closer in [('video',video.close if video else None),('backend',backend.close if backend else None)]:
            if closer:
                try:closer()
                except Exception:summary.update(status='HOST_ERROR',cleanup_error=traceback.format_exc())
        summary['wall_s']=time.monotonic()-began
        if video:summary['video_frames']=video.frames
        if summary['status']=='COMPLETED':
            paths=['robots/r3/commands.jsonl','robots/r3/frames.jsonl','eval_only/trajectory.jsonl','eval_only/camera.jsonl','eval_only/servo.jsonl']
            summary['comparison']={p:dict(original=sha(original/p),replay=sha(out/p)) for p in paths}
            summary['command_trajectory_match']=summary['comparison'][paths[0]]['original']==summary['comparison'][paths[0]]['replay']
            summary['all_physics_camera_match']=all(v['original']==v['replay'] for v in summary['comparison'].values())
            summary['video_sha256']=sha(video.output)
            if not summary['all_physics_camera_match']:summary['status']='REPLAY_MISMATCH'
        write(out.parent/'summary.json',summary);write(out.parent/'health.json',dict(status=summary['status'],wall_s=summary['wall_s']))
    print(summary['status'],summary.get('error',''))
    return int(summary['status'] in ('HOST_ERROR','REPLAY_MISMATCH'))


def main():
    p=argparse.ArgumentParser();p.add_argument('--expected-source-sha',required=True)
    p.add_argument('--original',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--path-check',action='store_true');a=p.parse_args()
    # Same archive/resource boundary as the S3 runner, which this older
    # egomap branch does not contain. No Mac model/render can reach run().
    import platform
    import shutil
    root=Path(__file__).resolve().parents[1]
    if platform.system()!='Linux' or platform.machine()!='x86_64' or os.environ.get('MUJOCO_GL')!='osmesa':
        raise ValueError('Oracle x86 OSMesa required')
    if root.name!=a.expected_source_sha:raise ValueError('committed source archive required')
    if len(a.output.parts)!=3 or a.output.parts[0]!='outputs' or a.output.parts[-1]!='raw':
        raise ValueError('runner output layout required')
    if (a.output.parent/'SOURCE_SHA').read_text().strip()!=a.expected_source_sha or a.output.exists():
        raise ValueError('source receipt mismatch or existing output')
    if os.getpriority(os.PRIO_PROCESS,0)!=0:raise ValueError('nice zero required')
    if shutil.disk_usage(a.output.parent).free<11*1024**3:raise ValueError('11GiB free required')
    if os.environ.get('LP_NUM_THREADS')!='4':raise ValueError('original rendering thread profile required')
    return run(a.original,a.output,a.expected_source_sha,path_check=a.path_check)


if __name__=='__main__':raise SystemExit(main())
