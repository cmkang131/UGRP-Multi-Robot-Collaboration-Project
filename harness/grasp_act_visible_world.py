"""Teacher world model from visible relative measurements and issued commands.

There is deliberately no simulator state argument. Absolute pose is an
unanchored command-odometry frame, unless the named comparison is selected.
"""
import math
from copy import deepcopy
from harness.grasp_act_contract import MEMORY_S
from harness.drive_model import CommandDriveModel, validate_options


SEARCH17_GAINS = (.75141578, .68525882, .71802760)


def command_delta(issued,dt,*,mode='off',drive_model_deadband_v1=False,model=None):
    if mode not in ('off','search17_fixed_v1'):raise ValueError('unknown search17 odometry')
    validate_options(drive_model_deadband_v1,search17_odometry=mode)
    if drive_model_deadband_v1:
        return (model if model is not None else CommandDriveModel()).delta(issued['wheels'],issued['duration_s'],dt)
    if model is not None:raise ValueError('drive model state requires drive_model_deadband_v1')
    a,b,c,d=[w*min(dt,t) for w,t in zip(issued['wheels'],issued['duration_s'])]
    gain=.0325*150*2*math.pi/60
    delta=(gain*(a+b+c+d)/4,gain*(-a+b+c-d)/4,gain*(-a+b-c+d)/(4*.1255))
    # Fixed offline least-squares gains; no runtime measured pose or velocity.
    # Fit: 19 even-index successful 752b0cbb episodes; held out: other 21.
    # See search17.md. Coordinator interpretation of fixed calibration is
    # user-unconfirmed; this option is never enabled by default.
    return tuple(x*g for x,g in zip(delta,SEARCH17_GAINS)) if mode!='off' else delta


class VisibleWorld:
    def __init__(self,rid,end,*,pose_source='issued',odometry='off',drive_model_deadband_v1=False):
        if pose_source not in ('issued','perfect_self_comparison'):raise ValueError('explicit pose source required')
        if odometry not in ('off','search17_fixed_v1'):raise ValueError('unknown search17 odometry')
        validate_options(drive_model_deadband_v1,search17_odometry=odometry)
        if (odometry!='off' or drive_model_deadband_v1) and pose_source!='issued':raise ValueError('drive correction requires issued pose')
        self.drive_model_deadband_v1=drive_model_deadband_v1
        self.drive_model=CommandDriveModel() if drive_model_deadband_v1 else None
        self.rid=rid;self.end=end;self.pose_source=pose_source;self.odometry=odometry
        self.pose=[0.,0.,0.];self.memory={};self.previous=None;self.previous_t=None

    def issue(self,command):self.previous=deepcopy(command)

    def observe(self,measurements,now,*,comparison_pose=None):
        if self.pose_source=='perfect_self_comparison':
            if comparison_pose is None:raise ValueError('explicit comparison pose missing')
            self.pose=list(comparison_pose)
        elif comparison_pose is not None:raise ValueError('GT self pose forbidden in default profile')
        elif self.previous is not None and self.previous_t is not None:
            dt=max(0.,now-self.previous_t) if self.drive_model_deadband_v1 else min(.15,max(0.,now-self.previous_t))
            x,y,a=command_delta(self.previous,dt,mode=self.odometry,
                                drive_model_deadband_v1=self.drive_model_deadband_v1,model=self.drive_model)
            co,si=math.cos(self.pose[2]),math.sin(self.pose[2])
            self.pose=[self.pose[0]+co*x-si*y,self.pose[1]+si*x+co*y,self.pose[2]+a]
        self.previous_t=now;seen=set()
        for m in measurements:
            if set(m)-{'id','kind','xyz','yaw','radius','top_z_bound_m','visible_n','probe_N','half_extents'}:raise ValueError('visible measurement whitelist')
            minimum=5 if m['kind']=='band' else max(1,math.ceil(m['probe_N']/3))
            if m['visible_n']<minimum:continue
            x,y,z=m['xyz'];co,si=math.cos(self.pose[2]),math.sin(self.pose[2])
            q={**deepcopy(m),'xyz':[self.pose[0]+co*x-si*y,self.pose[1]+si*x+co*y,z],
               'yaw':self.pose[2]+m['yaw'],'seen_t':now}
            self.memory[m['id']]=q;seen.add(m['id'])
        self.memory={k:v for k,v in self.memory.items() if now-v['seen_t']<=MEMORY_S}
        band=self.memory.get('band_'+self.end);beam=None
        if band is not None:
            x,y,z=band['xyz'];a=band['yaw'];offset=-.27 if self.end=='teal' else .27
            bx=x-offset*math.cos(a);by=y-offset*math.sin(a)
            # Known rigid shape supplies inferred geometry, not hidden GT.
            ends={role:[bx+d*math.cos(a),by+d*math.sin(a),z-.0086] for role,d in (('teal',-.27),('blue',.27))}
            beam={'pose':[bx,by,a],'ends':ends,'source':'visible band + known rigid shape','seen_t':band['seen_t']}
        robots={self.rid:{'pose':list(self.pose)}};objects={};walls=[]
        for key,m in self.memory.items():
            if m['kind']=='robot':robots[key]={'pose':[*m['xyz'][:2],m['yaw']],
                'radius':m.get('radius',.17),'top_z_bound_m':m.get('top_z_bound_m',.32)}
            if m['kind']=='wall':walls.append((*m['xyz'][:2],*m['half_extents'],m['yaw']))
            if m['kind']=='cargo':
                objects[key]={'xy':m['xyz'][:2],'radius':m['radius'],'top_z_bound_m':m['top_z_bound_m']}
        visibility={'visible_probes':next((m['visible_n'] for m in measurements if m['id']=='band_'+self.end),0),
                    'objects':[k for k in seen if k in objects],'peers':[k for k in seen if k in robots and k!=self.rid],
                    'observations':deepcopy(self.memory)}
        return {'t':now,'robots':robots,'objects':objects,'walls':walls,'beam':beam,'visibility':{self.rid:visibility},
                'scope':'visible_only; remembered objects expire at student memory horizon'}
