"""Teacher world model from visible relative measurements and issued commands.

There is deliberately no simulator state argument. Absolute pose is an
unanchored command-odometry frame, unless the named comparison is selected.
"""
import math
from copy import deepcopy
from harness.grasp_act_contract import MEMORY_S


def command_delta(issued,dt):
    a,b,c,d=[w*min(dt,t) for w,t in zip(issued['wheels'],issued['duration_s'])]
    gain=.0325*150*2*math.pi/60
    return gain*(a+b+c+d)/4,gain*(-a+b+c-d)/4,gain*(-a+b-c+d)/(4*.1255)


class VisibleWorld:
    def __init__(self,rid,end,*,pose_source='issued',profile=None,static_walls='off'):
        if static_walls not in ('off','persistent_walls_v1'):raise ValueError('unknown static wall mode')
        self.static_walls=static_walls
        if pose_source not in ('issued','perfect_self_comparison'):raise ValueError('explicit pose source required')
        self.rid=rid;self.end=end;self.pose_source=pose_source;self.profile=profile  # None: long beam
        self.pose=[0.,0.,0.];self.memory={};self.previous=None;self.previous_t=None

    def issue(self,command):self.previous=deepcopy(command)

    def observe(self,measurements,now,*,comparison_pose=None):
        if self.pose_source=='perfect_self_comparison':
            if comparison_pose is None:raise ValueError('explicit comparison pose missing')
            self.pose=list(comparison_pose)
        elif comparison_pose is not None:raise ValueError('GT self pose forbidden in default profile')
        elif self.previous is not None and self.previous_t is not None:
            x,y,a=command_delta(self.previous,min(.15,max(0.,now-self.previous_t)))
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
        self.memory={k:v for k,v in self.memory.items() if now-v['seen_t']<=MEMORY_S
                     or (self.static_walls=='persistent_walls_v1' and v['kind']=='wall')}
        band=self.memory.get('band_'+self.end);beam=None
        if band is not None:
            x,y,z=band['xyz'];a=band['yaw']
            centre,grasp,dz=(.27,.27,-.0086) if self.profile is None else (
                self.profile.band_center_m,self.profile.grasp_m,self.profile.end_z_offset_m)
            offset=-centre if self.end=='teal' else centre
            bx=x-offset*math.cos(a);by=y-offset*math.sin(a)
            # Known rigid shape supplies inferred geometry, not hidden GT.
            ends={role:[bx+d*math.cos(a),by+d*math.sin(a),z+dz] for role,d in (('teal',-grasp),('blue',grasp))}
            beam={'pose':[bx,by,a],'ends':ends,'source':'visible band + known rigid shape','seen_t':band['seen_t']}
        robots={self.rid:{'pose':list(self.pose)}};objects={};walls=[]
        for key,m in self.memory.items():
            if m['kind']=='robot':robots[key]={'pose':[*m['xyz'][:2],m['yaw']],
                'radius':m.get('radius',.17),'top_z_bound_m':m.get('top_z_bound_m',.32)}
            if m['kind']=='wall':walls.append((*m['xyz'][:2],*m['half_extents'],m['yaw']))
            if m['kind']=='cargo':
                objects[key]={'xy':m['xyz'][:2],'radius':m['radius'],'top_z_bound_m':m['top_z_bound_m']}
        visibility={'visible_probes':next((m['visible_n'] for m in measurements if m['id']=='band_'+self.end),0),
                    'objects':[k for k in seen if k in objects],'peers':[k for k in seen if k in robots and k!=self.rid]}
        return {'t':now,'robots':robots,'objects':objects,'walls':walls,'beam':beam,'visibility':{self.rid:visibility},
                'scope':('visible_only; static walls persist in issued odometry frame; dynamic memory expires'
                         if self.static_walls!='off' else 'visible_only; remembered objects expire at student memory horizon')}
