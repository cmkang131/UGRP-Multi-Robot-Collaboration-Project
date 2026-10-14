"""Observable local teacher with issued-command completion and real wheel pulses.

Truth is a demonstration-only label source. Navigation is explicitly outside
ACT. Once handed off, a lost target is propagated from issued wheels only;
the actual base pose cannot steer the gaze until the target is seen again.
"""
import math
from copy import deepcopy
from harness.grasp_act_contract import command,SERVOS,MEMORY_S
from sim.grasp_act_teacher import GraspTeacher,local,wrap,grasp_poses,STATION_M,XY_TOL_M,YAW_TOL_RAD
from sim.grasp_act_port import duty_wheels
from scripts.zone_teacher import FOLDED


def propagate_owned(point,issued,dt):
    # Nominal 65 mm wheel / 150 rpm kinematics; not calibrated odometry.
    # Only the preceding issued pulse is integrated, never measured motion.
    wheel=[w*min(dt,d) for w,d in zip(issued['wheels'],issued['duration_s'])]
    a,b,c,d=wheel;gain=.0325*150*2*math.pi/60
    dx= gain*(a+b+c+d)/4;dy=gain*(-a+b+c-d)/4
    yaw=gain*(-a+b-c+d)/(4*.1255)
    x,y,z=point;x-=dx;y-=dy;co,si=math.cos(yaw),math.sin(yaw)
    return [co*x+si*y,-si*x+co*y,z]


class VisibleOnlyGraspTeacher(GraspTeacher):
    def __init__(self,*args,**kwargs):
        kwargs.pop('profile',None)
        super().__init__(*args,profile='observable_v2',**kwargs)
        self.phase='approach';self.handoff=False;self.local_seen=None
        self.last_command=None;self.last_tick=None;self.command_complete=False
        self.ready_revocations=0;self.skill_started=None

    def _hold(self,now):
        return command({'t':now,'wheels':[0.]*4,'duration_s':[0.]*4,
                        'pwm':{str(s):self.sink.pwm[s] for s in SERVOS}})

    def _continuous(self,now,forward,left,turn):
        wheels,widths=duty_wheels([3.*forward,3.*left,.65*turn])
        value=self._hold(now);value.update(wheels=wheels,duration_s=widths)
        return command(value)

    def _observe(self,truth,now):
        from sim.grasp_act_gaze import slew
        from sim.grasp_act_visible_gaze import gaze_pose
        vis=truth['visibility'][self.rid];visible=vis['visible_probes']>=5
        self.visibility_counts['N']+=1;self.visibility_counts['visible']+=int(visible)
        self.blind_s=0. if visible else self.blind_s+.1;self.max_blind_s=max(self.max_blind_s,self.blind_s)
        if visible:
            g=truth['beam']['ends'][self.end]
            self.local_seen=[*local(truth['robots'][self.rid]['pose'],g),g[2]+.009]
            self.last_seen_t=now
        for iid in vis.get('objects',[]):self.observed_objects[iid]=deepcopy(truth['objects'][iid])
        for rid in vis.get('peers',[]):
            self.observed_peers[rid]=deepcopy(truth['robots'][rid]);self.observed_peers[rid]['seen_t']=now
        self.observed_peers={r:v for r,v in self.observed_peers.items() if now-v['seen_t']<=8.}
        if self.local_seen is not None and now-self.last_seen_t<=MEMORY_S:
            pose=truth['robots'][self.rid]['pose']
            occluders=[{'xy':local(pose,v['pose']),'radius':v.get('radius',.17),
                        'top_z_bound_m':v.get('top_z_bound_m',.32)}
                       for rid,v in truth['robots'].items() if rid!=self.rid]
            occluders += [{'xy':local(pose,v['xy']),'radius':v['radius'],
                          'top_z_bound_m':v['top_z_bound_m']}
                         for key,v in truth['objects'].items() if key!='beam_1']
            target=gaze_pose(self.local_seen,self.sink.pwm,occluders,visible=visible)
        else:
            # Clock starts at the issued local-skill instruction, not hidden
            # visibility events. Exactly the same elapsed scalar goes to ACT.
            age=now-self.skill_started
            near=age<2. or (age>=3.2 and int((age-3.2)/1.2)%2==0)
            target={**FOLDED,3:500 if near else 820,4:2500 if near else 2320,6:1500}
        self.sink.pwm.update(slew(self.sink.pwm,target));self.arm.commanded.update(self.sink.pwm)
        if visible:return None
        if self.last_seen_t is not None and now-self.last_seen_t<=MEMORY_S:return self._hold(now)
        if now-self.skill_started<3.2:return self._hold(now)
        return self._continuous(now,0.,0.,.45)

    def ready_geometry(self,truth):
        if truth['beam'] is None or truth['visibility'][self.rid]['visible_probes']<5:return False
        pose=truth['robots'][self.rid]['pose'];g=truth['beam']['ends'][self.end]
        x,y=local(pose,g);heading=truth['beam']['pose'][2]+(math.pi if self.end=='blue' else 0.)
        try:grasp_poses((x,y,g[2]))
        except ValueError:return False
        return math.hypot(x-STATION_M,y)<=XY_TOL_M and abs(wrap(heading-pose[2]))<=YAW_TOL_RAD

    def prepare_signal(self,truth,now):
        """Own teacher readiness; only a binary READY crosses the protocol."""
        if self.phase=='ready' and not self.ready_geometry(truth):
            self.ready_revocations+=1;self._set('align',now)
        return self.phase in ('ready','pick','complete')

    def step(self,truth,now,*,permit_pick=False):
        if self.local_seen is not None and self.last_command is not None and self.last_tick is not None:
            self.local_seen=propagate_owned(self.local_seen,self.last_command,min(.1,now-self.last_tick))
        value,done=self._step(truth,now,permit_pick=permit_pick)
        self.last_command=deepcopy(value);self.last_tick=now
        return value,done

    def remember_applied(self,value):
        # DART may alter the label command before it is sent. The observer
        # integrates what was actually issued, which is also in student input.
        self.last_command=deepcopy(command(value))

    def _step(self,truth,now,*,permit_pick):
        if not self.started:
            self.started=True;self.phase_t=now;self.skill_started=now
            self.arm.queue({**FOLDED,6:self.sink.pwm[6]},now,duration=.5)
        arms_done=self.arm.tick(now)
        self.folded_ready=arms_done and 500<=self.sink.pwm[3]<=960 and 2320<=self.sink.pwm[4]<=2500 and self.sink.pwm[5]==1320
        if self.command_complete:return self._hold(now),True
        if now-self.phase_t>60:
            self.outcome='phase_timeout';return self._hold(now),False
        self.rects=truth.get('walls',[])
        self.observed_objects=deepcopy(truth.get('objects',{}))
        self.observed_peers={r:{**deepcopy(v),'seen_t':now} for r,v in truth['robots'].items() if r!=self.rid}
        if self.phase in ('approach','align','ready'):
            if not arms_done:return self._hold(now),False
            search=self._observe(truth,now)
            if search is not None:
                if self.phase=='ready':self._set('align',now)
                return search,False
            if not arms_done:return self._hold(now),False
            pose=truth['robots'][self.rid]['pose'];g=truth['beam']['ends'][self.end]
            if not self.handoff and math.dist(pose[:2],g[:2])<=.8:
                self.handoff=True;self.skill_started=now
            self.prepare_signal(truth,now)
            if self.phase!='ready':
                value,ready=self._approach(truth,now)
                if ready:self._set('ready',now)
                return value,False
            if permit_pick:
                # Revalidate immediately before committing the fixed motion.
                if not self.ready_geometry(truth):self._set('align',now)
                else:self._queue_pick(truth,now)
            return self._hold(now),False
        if self.phase=='pick' and arms_done:
            self.command_complete=True;self._set('complete',now)
            # No contact, object height, GT timer or success field decides done.
            return self._hold(now),True
        return self._hold(now),False

    def diagnostic(self):
        return {**super().diagnostic(),'profile':'visible_only','command_complete':self.command_complete,
                'ready_revocations':self.ready_revocations,'handoff':self.handoff,
                'done_semantics':'own issued arm sequence complete; physical evaluation separate'}
