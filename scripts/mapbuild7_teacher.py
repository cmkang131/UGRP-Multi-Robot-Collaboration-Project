"""Adapter around byte-frozen6f057f7e SoloTeacher; native perception only.

Visible-only body-relative truth is the documented demonstration-teacher
exception. Held cargo coordinates are never read by this adapter. Camera FK,
map registration and driving never receive those teacher measurements.
"""
import math
import numpy as np


class VisibleTeacher:
    def __init__(self,m,plan,pwm,out,scene):
        from sim.grasp_act_solo_teacher import SoloTeacher,InputAudit,primitives
        from sim.grasp_act_solo_lookaround import SoloLookaround
        from sim.grasp_act_solo_lookback import LookbackObserver
        from audit_grasp_act_visibility import BandVisibility
        from warp_act_numpy import solve_grip_site_ik
        from sim.masterpi_camera_profile import scaled_camera_matrix,CAMERA_FISHEYE_D
        from scripts.zone_teacher import plan_path,proportional_drive
        class Eyes(BandVisibility):
            def __init__(self):
                self.np=np;self.model=m;self.K=scaled_camera_matrix(640,480);self.D=np.array(CAMERA_FISHEYE_D)
                self.groups=np.array([1,1,1,1,0,0],dtype=np.uint8);self.near=float(m.vis.map.znear*m.stat.extent)
                self.cameras={'r1':m.camera('r1__robot_cam').id};self.body_gids={}
        self.m=m;self.plan=plan;self.out=out;self.eyes=Eyes();self.audit=InputAudit();self.observed=[]
        self.body=m.body('cargo_'+plan['item_id']).id
        self.gids=[g for g in range(m.ngeom) if m.geom_bodyid[g]==self.body and m.geom_contype[g]]
        self.base=m.body('r1__robot').id;self.route_rejections=[];self.discs=[];self.scene=scene;self.ready_to_carry=False
        ops=primitives();ops.ik=solve_grip_site_ik
        def route(goal,context):
            path=plan_path((0.,0.),goal[:2],(-2.,2.,-2.,2.),self.discs,rects=self.observed,radius=.17)
            if not path:
                self.route_rejections.append(dict(category='no_visible_route',reason='frozen40000_node_search_no_path',
                    blocked_object='currently_visible_wall',minimum_gap_m=None,gap_status='not_measured'))
                return 0.,0.,0.
            point=next((p for p in path if math.hypot(*p)>=.06),goal[:2])
            cmd=proportional_drive((0.,0.,0.),goal[:2],point,goal[2]);return cmd['forward'],cmd['left'],cmd['turn']
        self.look=SoloLookaround({},ops=ops,truth_free_v1=True)
        self.teacher=SoloTeacher(plan['kind'],plan['role'],pwm,profile='solo_visible_only_v1',held_object_hidden_v1=True,
            setdown_lookaround_v1=True,lookaround=self.look,route=route,ops=ops,teacher_stability='align_relook_v1',
            reach_mode='pad_window_v2',rgb_lift_mode='solo_lift_lookback_v1',solo_lift_lookback_margin_v1=True)
        self.observer=LookbackObserver(plan['kind']);self.previous=self.teacher._hold(0.);self.tick=0;self.releasing=False
        self.lift_answer='unknown';self.evidence=[]

    def _save(self,tag,frame,now):
        import cv2,hashlib
        p=self.out/'lift-rgb';p.mkdir(exist_ok=True);file=p/(tag+'.png');cv2.imwrite(str(file),frame)
        return dict(path=str(file),t=now,sha256=hashlib.sha256(file.read_bytes()).hexdigest(),pixel_sha256=hashlib.sha256(frame.tobytes()).hexdigest(),shape=list(frame.shape))

    def step(self,now,rgb,data):
        import cv2
        from sim.grasp_act_solo_teacher import wrap
        t=self.teacher;m=self.m
        # All state access below is confined to the current-visible teacher
        # perception exception; lazy InputAudit blocks held/hidden callbacks.
        seen,total=self.eyes.region_visible(data,'r1',self.gids)
        R=data.xmat[self.base].reshape(3,3);yaw=math.atan2(R[1,0],R[0,0]);c,s=math.cos(yaw),math.sin(yaw)
        def measurement():
            b=data.body('cargo_'+self.plan['item_id']);rot=b.xmat.reshape(3,3)
            point=b.xpos+rot@np.array([0.,0.,t.spec.grip_z_m-.016]);dx,dy=point[:2]-data.xpos[self.base,:2]
            return dict(xyz=[float(c*dx+s*dy),float(-s*dx+c*dy),float(point[2])],yaw=wrap(math.atan2(rot[1,0],rot[0,0])-yaw))
        value=self.audit.measure(t.phase,visible_n=seen,probe_N=total,holding=t.holding,read_relative=measurement)
        if self.tick%5==0:
            self.observed=[];self.discs=[]
            bodies={x.item_id:x.body for x in self.scene.cargo}
            bodies.update({i:x['body_name'] for i,x in self.scene.config['setup_only']['objects'].items()})
            bodies.update({rid:rid+'__robot' for rid in ('r2','r3')})
            for iid,name in bodies.items():
                if iid==self.plan['item_id']:continue
                bid=m.body(name).id;gids=self.eyes._body_geoms(bid);n,N=self.eyes.region_visible(data,'r1',gids)
                if N and n>=math.ceil(N/3):
                    dx,dy=data.xpos[bid,:2]-data.xpos[self.base,:2]
                    radius=(.17 if iid in ('r2','r3') else max((float(np.linalg.norm(data.geom_xpos[g,:2]-data.xpos[bid,:2]))+float(m.geom_rbound[g]) for g in gids),default=.2))
                    self.discs.append((c*dx+s*dy,-s*dx+c*dy,radius))
            for gid in range(m.ngeom):
                if 'wall' not in (m.geom(gid).name or ''):continue
                n,N=self.eyes.region_visible(data,'r1',[gid])
                if N and n>=math.ceil(N/3):
                    dx,dy=data.geom_xpos[gid,:2]-data.xpos[self.base,:2];rot=data.geom_xmat[gid].reshape(3,3)
                    self.observed.append((c*dx+s*dy,-s*dx+c*dy,*map(float,m.geom_size[gid,:2]),wrap(math.atan2(rot[1,0],rot[0,0])-yaw)))
        bgr=cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR);answer={'answer':'unknown'}
        if t.phase in ('verify_lift','hold'):answer=self.observer.observe(bgr,{**self.previous,'t':now},complete=True,save=self._save)
        elif t.phase=='lift':self.observer.observe(bgr,{**self.previous,'t':now},complete=False,save=self._save)
        self.lift_answer=answer.get('answer','unknown')
        if t.phase=='lower' and not self.look.armed:self.look.arm()
        phase=t.phase
        if not self.releasing and phase=='hold' and now-t.phase_t>=3.-1e-8 and self.lift_answer=='yes':
            self.ready_to_carry=True
            return self.pause(now),False,dict(phase=phase,visible_n=seen,probe_N=total,rgb=answer,input_audit=self.audit.record())
        cmd,done=t.step(now,measurement=value,rgb_holding=self.lift_answer,own_rgb=lambda:rgb)
        if phase in ('align','approach') and t.phase=='hover':self.observer.start(bgr,{**self.previous,'t':now},self._save)
        self.observer.issue(cmd,t.phase);self.previous=cmd;self.tick+=1
        return cmd,done,dict(phase=t.phase,visible_n=seen,probe_N=total,rgb=answer,input_audit=self.audit.record())

    def pause(self,now):
        # The workflow owns transport between grasp and release. Freeze the
        # teacher's skill clock using issued time only; no hidden success gate.
        self.teacher.previous_t=now;self.teacher.previous=self.teacher._hold(now);self.previous=self.teacher.previous
        self.teacher.phase_t=now
        return self.previous

    def release(self,now):
        # Start the SAME frozen low/open/retract/backoff/lookaround sequence at
        # the new map-selected place. Do not replay a CPU trajectory.
        t=self.teacher;t.previous_t=now-.1;t.previous=t._hold(now-.1);self.previous=t.previous
        t._queue(t.high,now,.8,.2);t._queue(t.low,now,.8,.2);t._set('lower',now)
        self.releasing=True
