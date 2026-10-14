"""Evaluation-only reconstruction of recorded camera views. Never steps physics.

The band has 15 inset top-surface probes. A probe must be inside BOTH the
source pinhole render and its raw-fisheye image, and be the first visible ray
intersection. This measures geometric availability, not visual recognition.
"""
import argparse, hashlib, json, math, subprocess
from collections import defaultdict
from pathlib import Path


def read(path, lines=False):
    path=Path(path)
    if not path.exists():path=Path(str(path)+'.zst')
    raw=path.read_bytes()
    if path.suffix=='.zst':raw=subprocess.check_output(['zstd','-qdc'],input=raw)
    return [json.loads(x) for x in raw.splitlines()] if lines else json.loads(raw)


class BandVisibility:
    def __init__(self, model):
        import numpy as np
        from sim.masterpi_camera_profile import scaled_camera_matrix,CAMERA_FISHEYE_D
        self.np=np;self.model=model;self.K=scaled_camera_matrix(640,480)
        self.D=np.array(CAMERA_FISHEYE_D)
        self.groups=np.array([1,1,1,1,0,0],dtype=np.uint8)
        self.near=float(model.vis.map.znear*model.stat.extent)
        self.cameras={r:model.camera(r+'__robot_cam').id for r in ('r1','r2')}
        self.bands={r:model.geom('cargo_beam_1__band_'+s).id for r,s in (('teal','neg'),('blue','pos'))}
        self.probes={}
        for role,gid in self.bands.items():
            size=model.geom_size[gid]
            self.probes[role]=np.array([(x*size[0],y*size[1],size[2]+1e-6)
                for x in (-.9,-.45,0.,.45,.9) for y in (-.9,0.,.9)])


    def restore_recorded_runtime_mount(self):
        # Frozen runner uses bare v7 build_world, NOT s2_realism_camera_binding.
        # NamespacedMasterPi._configure_measured_robot_camera overwrites XML.
        from sim.masterpi_camera_profile import CAMERA_LOCAL_POS_M,CAMERA_LOCAL_QUAT_WXYZ
        for cid in self.cameras.values():
            self.model.cam_pos[cid]=CAMERA_LOCAL_POS_M
            self.model.cam_quat[cid]=CAMERA_LOCAL_QUAT_WXYZ

    def measure(self,data,rid,role):
        import cv2,mujoco
        np=self.np;cid=self.cameras[rid];gid=self.bands[role]
        points=data.geom_xpos[gid]+self.probes[role]@data.geom_xmat[gid].reshape(3,3).T
        camera=(points-data.cam_xpos[cid])@data.cam_xmat[cid].reshape(3,3)
        optical=camera*np.array([1.,-1.,-1.]);z=optical[:,2]
        pinhole=optical[:,:2]/np.maximum(z[:,None],1e-12)
        uv=pinhole*np.diag(self.K)[:2]+self.K[:2,2]
        raw,_=cv2.fisheye.projectPoints(optical.reshape(-1,1,3),np.zeros(3),np.zeros(3),self.K,self.D)
        raw=raw.reshape(-1,2)
        inside=(z>self.near)&(uv[:,0]>=0)&(uv[:,0]<640)&(uv[:,1]>=0)&(uv[:,1]<480)&(raw[:,0]>=0)&(raw[:,0]<640)&(raw[:,1]>=0)&(raw[:,1]<480)
        seen=0;occluders=[]
        for i in np.flatnonzero(inside):
            delta=points[i]-data.cam_xpos[cid];distance=float(np.linalg.norm(delta));direction=delta/distance
            # Clip in camera depth, exactly as the renderer's near plane.
            skip=self.near*distance/z[i];origin=data.cam_xpos[cid]+skip*direction
            hit=np.array([-1],dtype=np.int32)
            ray=mujoco.mj_ray(self.model,data,origin,direction,self.groups,True,-1,hit)
            if int(hit[0])==gid and abs(ray-(distance-skip))<.003:seen+=1
            else:occluders.append(self.model.geom(int(hit[0])).name if hit[0]>=0 else 'no_hit')
        return {'in_frame':bool(inside.any()),'visible':seen>0,'visible_probes':seen,
                'in_frame_probes':int(inside.sum()),'probe_N':len(points),'occluders':sorted(set(occluders))}

    def body_visible(self,data,rid,body_name):
        """Teacher-only exposure check for peers/cargo; never a student input."""
        import cv2,mujoco
        np=self.np;cid=self.cameras[rid];bid=self.model.body(body_name).id
        gids=[]
        for gid in range(self.model.ngeom):
            b=int(self.model.geom_bodyid[gid])
            while b and b!=bid:b=int(self.model.body_parentid[b])
            if b==bid and self.groups[self.model.geom_group[gid]] and self.model.geom_rgba[gid,3]>.1:gids.append(gid)
        if not gids:return False
        # Largest visual parts first; avoid testing every decorative wheel pin.
        gids=sorted(gids,key=lambda g:-self.model.geom_rbound[g])[:8];owned=set(gids)
        points=data.geom_xpos[gids]
        optical=((points-data.cam_xpos[cid])@data.cam_xmat[cid].reshape(3,3))*np.array([1.,-1.,-1.])
        for point,p in zip(points,optical):
            if p[2]<=self.near:continue
            uv=p[:2]/p[2]*np.diag(self.K)[:2]+self.K[:2,2]
            raw,_=cv2.fisheye.projectPoints(p.reshape(1,1,3),np.zeros(3),np.zeros(3),self.K,self.D)
            if not (0<=uv[0]<640 and 0<=uv[1]<480 and 0<=raw[0,0,0]<640 and 0<=raw[0,0,1]<480):continue
            delta=point-data.cam_xpos[cid];distance=float(np.linalg.norm(delta));direction=delta/distance
            origin=data.cam_xpos[cid]+self.near*distance/p[2]*direction;hit=np.array([-1],dtype=np.int32)
            mujoco.mj_ray(self.model,data,origin,direction,self.groups,True,-1,hit)
            if hit[0]<0:continue
            b=int(self.model.geom_bodyid[hit[0]])
            while b and b!=bid:b=int(self.model.body_parentid[b])
            if b==bid:return True
        return False


def stage(label,pick_t):
    phase=label['teacher_phase'];now=label['clean_teacher_command']['t']
    if phase=='pick':
        dt=now-pick_t
        if dt<1.1:return 'hover'
        if dt<2.62:return 'descent'
        if dt<3.92:return 'grasp'
        return 'lift'
    return {'approach':'approach','align':'alignment','ready':'ready','verify':'lift','done':'done'}.get(phase,phase)


def audit(gate,out):
    import mujoco,numpy as np
    out.mkdir(parents=True,exist_ok=False)
    counts=defaultdict(lambda:{'visible_n':0,'in_frame_n':0,'N':0,'moving_n':0,'blind_moving_n':0})
    episodes=[];sources=[];raw_path=out/'samples.jsonl'
    with raw_path.open('w') as stream:
        for entry in read(gate)['rows']:
            root=Path(entry['raw'].split(':',1)[1]);model=mujoco.MjModel.from_xml_path(str(root/'scene.xml'))
            data=mujoco.MjData(model);evaluator=BandVisibility(model)
            evaluator.restore_recorded_runtime_mount()
            rows=read(root/'eval-only.jsonl',True);plan=read(root/'plan.json')
            labels={r:read(root/f'teacher-{r}.jsonl',True) for r in plan['roles']}
            if any(len(ls)!=len(rows) for ls in labels.values()):raise ValueError('sample alignment mismatch')
            for name in ('scene.xml','plan.json','eval-only.jsonl','teacher-r1.jsonl','teacher-r2.jsonl'):
                p=root/name
                if not p.exists():p=Path(str(p)+'.zst')
                sources.append({'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
            previous={};pick={};blind={r:0. for r in labels};maxblind=dict(blind);blindgap=dict(blind);maxgap=dict(blind)
            for i,row in enumerate(rows):
                data.qpos[:]=row['joints'];mujoco.mj_kinematics(model,data);mujoco.mj_camlight(model,data)
                for rid,role in plan['roles'].items():
                    label=labels[rid][i];cmd=label['applied_command']
                    if abs(cmd['t']-row['t'])>1e-6:raise ValueError('truth/action time mismatch')
                    if label['teacher_phase']=='pick' and rid not in pick:pick[rid]=row['t']
                    phase=stage(label,pick.get(rid,row['t']));vis=evaluator.measure(data,rid,role)
                    moving=any(abs(x)>1e-8 for x in cmd['drive']) or (rid in previous and cmd['pwm']!=previous[rid]['pwm'])
                    previous[rid]=cmd
                    blind[rid]=blind[rid]+.1 if moving and not vis['visible'] else 0.
                    blindgap[rid]=blindgap[rid]+.1 if not vis['visible'] else 0.
                    maxblind[rid]=max(maxblind[rid],blind[rid]);maxgap[rid]=max(maxgap[rid],blindgap[rid])
                    for key in ('all',phase):
                        c=counts[key];c['N']+=1;c['visible_n']+=int(vis['visible']);c['in_frame_n']+=int(vis['in_frame'])
                        c['moving_n']+=int(moving);c['blind_moving_n']+=int(moving and not vis['visible'])
                    stream.write(json.dumps({'episode':entry['index'],'robot':rid,'t':row['t']-rows[0]['t'],
                        'phase':phase,'moving':moving,**vis},separators=(',',':'))+'\n')
            episodes.append({'index':entry['index'],'max_contiguous_blind_motion_s':maxblind,'max_unseen_gap_s':maxgap})
            print(json.dumps(episodes[-1]),flush=True)
    raw=raw_path.read_bytes();compressed=subprocess.check_output(['zstd','-q','-c'],input=raw)
    assert subprocess.check_output(['zstd','-qdc'],input=compressed)==raw
    packed=Path(str(raw_path)+'.zst');packed.write_bytes(compressed);raw_path.unlink()
    result={'scope':'evaluation_only; recorded qpos; kinematics and rays; no physics stepping or student input',
        'gate_path':str(gate),'gate_sha256':hashlib.sha256(gate.read_bytes()).hexdigest(),'episode_N':len(episodes),
        'definition':'any of 15 inset band top-surface probes in source pinhole and raw fisheye frame, first ray hit assigned band; groups 4/5 hidden, original near clip',
        'limitations':['geometric availability is not detector recognition','pick substages reconstructed from fixed ArmSequence timings; <=0.1 s boundary uncertainty','commanded motion is not measured motion'],
        'camera':'frozen runner runtime mount from masterpi_camera_profile (overwrites XML v3 mount); unchanged measured fisheye K/D at 640x480',
        'stages':dict(counts),'episodes':episodes,'sources':sources,
        'samples':{'path':str(packed),'sha256':hashlib.sha256(compressed).hexdigest(),'decoded_sha256':hashlib.sha256(raw).hexdigest()}}
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'stages':dict(counts),'episode_N':len(episodes)}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--gate',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    audit(a.gate,a.out)
