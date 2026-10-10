"""S3 recorded actuator replay, Oracle x86/OSMesa, evaluation-only video."""
from __future__ import annotations

import argparse
import bisect
import hashlib
import itertools
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import traceback

ROBOTS = ('r1', 'r2', 'r3')
BASE_SHA = '98fd3ffed52f91db0130124024d38f09bf8208f4'
ORIGINALS = {'s3fix21-on-pair-c0-r1': '71c656e726235b11a2a45562eecbd17f6aa67b78',
             's3fix21-on-pair-c3-r1': '71c656e726235b11a2a45562eecbd17f6aa67b78',
             's3fix21-multi-three-c5-r2': '9d50e37d3415b2cfe065fe836df855befee664ed'}
# These two controller/route runners are never imported by this replay.
UNUSED_RUNNERS = {'scripts/run_s3_integer_carry.py', 'scripts/run_s3_stage_origin.py'}
STAGES = {'align_start': '정렬', 'align': '정렬', 'pregrasp_descend': '집기',
          'wait_close': '집기', 'grasp': '집기', 'wait_lift': '들기', 'lift': '들기',
          'wait_carry': '운반', 'carry': '운반', 'wait_lower': '운반', 'refix_decide': '운반',
          'lower': '내려놓기', 'wait_open': '내려놓기', 'cp_open': '내려놓기'}


def read(p):
    return json.loads(Path(p).read_text())


def rows(p):
    return [json.loads(l) for l in Path(p).read_text().splitlines()]


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def write(p, value):
    Path(p).write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n')


def audit_tape(raw):
    """Keep every actuator row, including duplicate holds and same-robot order.

    Original S3 has separate robot logs, not a global command journal. No
    physics tick occurs between issues. Cross-robot writes commute, except the
    coupled-port grip predicate, which must be invariant on motion ticks.
    """
    start = rows(raw/'robots/r1/frames.jsonl')[0]['sim_time']
    end = round(start+read(raw/'result.json')['check_sim_s'], 9)
    groups = {}
    grips = {}
    for rid in ROBOTS:
        previous = -float('inf')
        for row in rows(raw/f'robots/{rid}/commands.jsonl'):
            t = row['t']
            if t < previous or t > end+1e-8:
                raise ValueError('nonchronological or out-of-range actuator log')
            previous = t
            if t < start-1e-8:
                if row['kind'] == 'initial_servo_command':
                    grips[rid] = row['pulses']['1']
                elif row['kind']=='arm' and row['servo_id']==1:
                    grips[rid] = row['pulse']
                continue
            tick = round((t-start)/.05)
            if abs(start+tick*.05-t)>1e-8 or row['kind']=='initial_servo_command':
                raise ValueError('command outside original 20Hz clock')
            groups.setdefault(tick, []).append(dict(robot_id=rid, t=t,
                action={k:v for k,v in row.items() if k!='t'}))
    for tick in sorted(groups):
        group = groups[tick]
        if any(r['action']['kind'] in ('drive','mecanum') for r in group):
            for r in group:
                a = r['action']; rid = r['robot_id']
                if a['kind']=='arm' and a['servo_id']==1 and rid in ('r1','r2'):
                    if (a['pulse']<=1600) != (grips[rid]<=1600):
                        raise ValueError('ambiguous cross-robot coupled-port transition')
        for r in group:
            a = r['action']
            if a['kind']=='arm' and a['servo_id']==1:
                grips[r['robot_id']] = a['pulse']
    return start, end, groups


class Timeline:
    def __init__(self, states):
        self.rows = states
        self.times = [r['t'] for r in states]

    def at(self, t):
        i = bisect.bisect_right(self.times, t+1e-8)-1
        return self.rows[i] if i>=0 else None


def stage_label(states, *, finished_single=False):
    if finished_single:
        return '내려놓기 (완료)'
    labels = {rid: STAGES[row['state']] for rid,row in states.items()}
    if not labels:
        return '정렬'
    if len(set(labels.values()))==1:
        return next(iter(labels.values()))
    return ' · '.join(rid+' '+s for rid,s in labels.items())


class Video:
    """All camera fitting and state reads happen on an independent observer."""
    def __init__(self, host, name, start, stages, font):
        import mujoco
        import numpy as np
        from PIL import ImageFont
        self.mj, self.np = mujoco, np
        self.name, self.start, self.stages = name, start, stages
        self.model = mujoco.MjModel.from_xml_path(str(host.out/'scene.xml'))
        self.model.vis.global_.offwidth = max(960, self.model.vis.global_.offwidth)
        self.model.vis.global_.offheight = max(444, self.model.vis.global_.offheight)
        self.model.vis.global_.fovy = 40
        self.data = mujoco.MjData(self.model)
        self.renderer = mujoco.Renderer(self.model, height=444, width=960)
        self.camera = mujoco.MjvCamera()
        self.camera.type = mujoco.mjtCamera.mjCAMERA_FREE
        self.camera.azimuth, self.camera.elevation = 65., -45.
        self.camera.distance = 2.
        self.font = ImageFont.truetype(str(font), 21)
        self.next_t, self.frames, self.minimum_coverage = start, 0, 1.
        self.output = host.out.parent/'overview.mp4'
        roots = {int(self.model.body(r+'__robot').id) for r in ('r1','r2')}
        beam = next(v['body_name'] for v in host.objects.values() if v['kind']=='long_beam')
        self.beam_body = int(self.model.body(beam).id); roots.add(self.beam_body)
        self.geometry = []
        for g in range(self.model.ngeom):
            b = int(self.model.geom_bodyid[g])
            while b and b not in roots:
                b = int(self.model.body_parentid[b])
            if b not in roots or self.model.geom_rgba[g,3]<=0 or self.model.geom_group[g]>2:
                continue
            if self.model.geom_type[g] == mujoco.mjtGeom.mjGEOM_MESH:
                mesh = int(self.model.geom_dataid[g]); i = int(self.model.mesh_vertadr[mesh])
                v = self.model.mesh_vert[i:i+int(self.model.mesh_vertnum[mesh])]
                lo,hi = v.min(axis=0),v.max(axis=0)
            else:
                size = self.model.geom_size[g].copy()
                kind = self.model.geom_type[g]
                if kind == mujoco.mjtGeom.mjGEOM_SPHERE:
                    size[:] = size[0]
                elif kind in (mujoco.mjtGeom.mjGEOM_CYLINDER,mujoco.mjtGeom.mjGEOM_CAPSULE):
                    size[:] = (size[0],size[0],size[1]+(size[0] if kind==mujoco.mjtGeom.mjGEOM_CAPSULE else 0))
                lo,hi = -size,size
            corners = np.array(list(itertools.product(*zip(lo,hi))))
            self.geometry.append((g,corners))
        if not self.geometry:
            raise ValueError('observer carrier/beam geometry missing')
        self.trace = (host.out/'eval_only/overview-camera.jsonl').open('x')
        self.process = subprocess.Popen([shutil.which('ffmpeg'), '-nostdin','-n','-v','error',
            '-f','rawvideo','-pix_fmt','rgb24','-s','1280x480','-r','20','-i','-',
            '-an','-c:v','libx264','-threads','1','-preset','veryfast','-crf','20',
            '-pix_fmt','yuv420p','-movflags','+faststart',str(self.output)],stdin=subprocess.PIPE)

    def fit(self):
        np = self.np
        points = np.concatenate([c@self.data.geom_xmat[g].reshape(3,3).T+self.data.geom_xpos[g]
                                 for g,c in self.geometry])
        self.camera.lookat[:] = (points.max(axis=0)+points.min(axis=0))/2
        # Keep the oblique view relative to the beam's long axis while tracking.
        axis = self.data.xmat[self.beam_body].reshape(3,3)[:,0]
        self.camera.azimuth = float(np.degrees(np.arctan2(axis[1],axis[0])))+65.
        self.renderer.update_scene(self.data,camera=self.camera)
        cams = self.renderer.scene.camera
        forward = np.mean([c.forward for c in cams],axis=0); forward /= np.linalg.norm(forward)
        up = np.mean([c.up for c in cams],axis=0); up /= np.linalg.norm(up)
        right = np.cross(forward,up)
        rel = points-self.camera.lookat
        h = np.tan(np.radians(40/2)); w = h*960/444
        self.camera.distance = float(max(np.max(abs(rel@right)/(.94*w)-rel@forward),
                                         np.max(abs(rel@up)/(.94*h)-rel@forward),.25))
        self.renderer.update_scene(self.data,camera=self.camera)
        eye = np.mean([c.pos for c in self.renderer.scene.camera],axis=0)
        view = points-eye; depth = view@forward
        pix = np.column_stack((480+(view@right)/(depth*w)*480,
                               222-(view@up)/(depth*h)*222))
        low,high = pix.min(axis=0),pix.max(axis=0)
        coverage = float(np.prod(high-low)/(1280*480))
        if coverage < 1/3 or np.any(low<-1) or np.any(high>[961,445]):
            raise ValueError(f'observer framing must show all carriers/beam and fill >=1/3: {coverage}, {low}, {high}')
        self.minimum_coverage = min(self.minimum_coverage,coverage)
        return dict(bbox_xyxy_px=[*low.tolist(),*high.tolist()],full_frame_bbox_fraction=coverage,
            camera_lookat=self.camera.lookat.tolist(),distance=float(self.camera.distance),
            azimuth=float(self.camera.azimuth),elevation=float(self.camera.elevation))

    def frame(self, host, own):
        from PIL import Image,ImageDraw
        if host.now+1e-8<self.next_t:
            return
        self.mj.mj_copyData(self.data,host.world.model,host.world.data)
        framing = self.fit()
        canvas = Image.new('RGB',(1280,480),'#101820')
        canvas.paste(Image.fromarray(self.renderer.render()),(0,36))
        draw = ImageDraw.Draw(canvas)
        st = self.stages.at(host.now)
        previous_lower = any(r['t']<host.now and any(v['state']=='cp_open' for v in r['robots'].values())
                             for r in self.stages.rows)
        done = 'on-pair' in self.name and previous_lower and st and all(v['state']=='align' for v in st['robots'].values())
        label = stage_label(st['robots'] if st else {},finished_single=done)
        title = self.name.removeprefix('s3fix21-')
        draw.text((8,7),title,font=self.font,fill='#f4f8ff')
        draw.text((360,7),label,font=self.font,fill='#f9d36b')
        draw.text((850,7),f'SIM+{host.now-self.start:.2f}s (t={host.now:.2f}s)',font=self.font,fill='#f4f8ff')
        for i,rid in enumerate(('r1','r2')):
            y = 36+i*222
            draw.text((970,y+2),rid+' own RGB',font=self.font,fill='#f4f8ff')
            im = Image.fromarray(own[rid][1]); im.thumbnail((320,194),Image.Resampling.LANCZOS)
            canvas.paste(im,(960+(320-im.width)//2,y+28+(194-im.height)//2))
        self.process.stdin.write(self.np.asarray(canvas).tobytes())
        self.trace.write(json.dumps(dict(t=host.now,stage=label,**framing),ensure_ascii=False)+'\n')
        self.frames += 1; self.next_t += .2

    def close(self):
        try:
            self.process.stdin.close()
            if self.process.wait(timeout=30) or not self.frames:
                raise RuntimeError('overview encoder failed')
        finally:
            if self.process.poll() is None:
                self.process.kill(); self.process.wait()
            self.trace.close(); self.renderer.close()


def run(original,output,execution_sha,font,*,path_check=False):
    import numpy as np
    import mujoco
    from sim.s3_setdown import PhysicsBackend
    from scripts.run_s3_alignment_probe import restore_scene
    from harness.zone_pair_highpose_exact_speedups import install
    import sys
    if any(p[:-3].replace('/', '.') in sys.modules for p in UNUSED_RUNNERS):
        raise ValueError('changed controller runner entered replay import graph')
    raw = original/'raw'; b = read(raw/'bundle.json')
    if original.name not in ORIGINALS or b['source_sha']!=ORIGINALS[original.name]:
        raise ValueError('wrong original S3 source/run')
    start,end,groups = audit_tape(raw)
    root = Path(__file__).resolve().parents[1]; checked = {}; unused = {}
    for p,h in b['source_sha256'].items():
        if p.startswith(('sim/','harness/','scripts/','configs/')):
            actual = sha(root/p)
            if actual!=h:
                if p not in UNUSED_RUNNERS:
                    raise ValueError('original replay dependency changed: '+p)
                unused[p] = dict(original=h,current=actual,imported=False)
            else:
                checked[p] = h
    stages = Timeline(read(raw/'stage-states.json'))
    eval_states = {round(r['t'],9):r['states'] for r in rows(raw/'eval_only/setdown.jsonl')}
    frame_times = {round(r['sim_time'],9) for r in rows(raw/'robots/r1/frames.jsonl')}
    output.mkdir(parents=True,exist_ok=False)
    write(output/'original-bundle.json',b)
    summary = dict(status='RUNNING',name=original.name,execution_sha=execution_sha,base_sha=BASE_SHA,
        original_source_sha=b['source_sha'],original_path=str(original),source_sha256=checked,
        changed_unused_runners=unused,original_outcome=read(raw/'result.json'),
        evaluation_only=True,model_calls=0,controller_run=False,physics_correction=False,
        same_tick_order='r1 then r2, each original per-robot order preserved; coupled grip predicate audited invariant on all motion ticks',
        start_sim_s=start,end_sim_s=end,playback_speed=4,width=1280,height=480,
        font_sha256=sha(font),loadavg_start=os.getloadavg())
    backend=video=None; began=time.monotonic(); _,undo=install('v98-exact-v6')
    try:
        backend=PhysicsBackend(b,output,seed=b['seed'])
        backend.states_getter=lambda:eval_states.get(round(backend.now,9),{})
        backend.reset(b['reset_cap_s']); restore_scene(backend,read(raw/'eval_only/stage-setup.json'))
        if abs(backend.now-start)>1e-8:
            raise ValueError('stage start differs')
        spec=mujoco.mjtState.mjSTATE_INTEGRATION
        state=np.empty(mujoco.mj_stateSize(backend.world.model,spec))
        mujoco.mj_getState(backend.world.model,backend.world.data,state,spec)
        summary['initial_state_exact']=bool(np.array_equal(state,np.load(raw/'eval_only/stage-integration-state.npz')['state']))
        if not summary['initial_state_exact']:
            raise ValueError('initial state differs; no correction applied')
        backend.set_deadline(end)
        video=Video(backend,original.name,start,stages,font)
        steps=round((end-start)/.05)
        if path_check:
            steps=min(steps,1)
        for i in range(steps+1):
            backend.eval_sample()
            if round(backend.now,9) in frame_times:
                video.frame(backend,backend.capture())
            for row in groups.get(i,[]):
                backend.issue(row['robot_id'],row['action'])
            if i%20==0:
                write(output.parent/'health.json',dict(status='RUNNING',relative_sim_s=round(backend.now-start,8),
                    wall_s=time.monotonic()-began,video_frames=video.frames,pid=os.getpid(),loadavg=os.getloadavg()))
            if i<steps:
                backend.advance_to(start+(i+1)*.05)
        summary['status']='PATH_CHECK' if path_check else 'COMPLETED'
    except Exception:
        summary.update(status='HOST_ERROR',error=traceback.format_exc())
    finally:
        for name,closer in [('video',video.close if video else None),('backend',backend.close if backend else None),('speedups',undo)]:
            if closer:
                try:closer()
                except Exception:
                    summary.update(status='HOST_ERROR')
                    summary.setdefault('cleanup_errors',{})[name]=traceback.format_exc()
        if video:
            summary.update(video_frames=video.frames,minimum_full_frame_bbox_fraction=video.minimum_coverage)
        summary.update(wall_s=time.monotonic()-began,loadavg_end=os.getloadavg())
        if summary['status']=='COMPLETED':
            paths = [f'robots/{r}/commands.jsonl' for r in ROBOTS]
            paths += [f'eval_only/{r}/trajectory.jsonl' for r in ROBOTS]
            paths += [f'eval_only/{r}/render_camera.jsonl' for r in ROBOTS]
            paths += [f'robots/{r}/frames.jsonl' for r in ROBOTS]
            summary['comparison']={p:dict(original=sha(raw/p),replay=sha(output/p)) for p in paths}
            for kind,prefix in [('command_trajectory','robots/'),('evaluation_trajectory','eval_only/')]:
                suffix='commands.jsonl' if kind=='command_trajectory' else 'trajectory.jsonl'
                summary[kind+'_match']=all(v['original']==v['replay'] for p,v in summary['comparison'].items()
                    if p.startswith(prefix) and p.endswith(suffix))
            summary['camera_and_qpos_match']=all(v['original']==v['replay'] for p,v in summary['comparison'].items()
                if p.endswith(('render_camera.jsonl','frames.jsonl')))
            summary['video_sha256']=sha(video.output)
            if not all(summary[k] for k in ('command_trajectory_match','evaluation_trajectory_match','camera_and_qpos_match')):
                summary['status']='REPLAY_MISMATCH'
        write(output.parent/'summary.json',summary)
        write(output.parent/'health.json',dict(status=summary['status'],wall_s=summary['wall_s']))
    print(json.dumps({k:summary.get(k) for k in ('name','status','command_trajectory_match','evaluation_trajectory_match','camera_and_qpos_match','error')}))
    return int(summary['status'] in ('HOST_ERROR','REPLAY_MISMATCH'))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--expected-source-sha',required=True)
    p.add_argument('--original',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--font',type=Path,required=True)
    p.add_argument('--path-check',action='store_true')
    a=p.parse_args()
    from scripts.run_s3_x86_probe import archive_guard
    archive_guard(a.expected_source_sha,a.output)
    if os.environ.get('LP_NUM_THREADS')!='4':
        raise ValueError('original LP_NUM_THREADS=4 required')
    return run(a.original,a.output,a.expected_source_sha,a.font,path_check=a.path_check)


if __name__=='__main__':
    raise SystemExit(main())
