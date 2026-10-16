"""Opt-in persistent loaded route, own estimated pose + authored map only.

Provenance: experiments/2026-10-16-reloc21/references.md. No truth/plant port.
Keep collision-free targets until reached, rather than reanchoring a .05m
grid every second and chasing its first .12m waypoint. Every shortcut and
issued tick retains reloc20's strict swept load enclosure.
"""
import math

from harness.reloc20_motion import GRID_M, heading_forward, wrap

OPTION = 'reloc21_route_progress_v1'
FULL = 'reloc21_complete_plan_v1'
ARRIVAL_M = .025  # unchanged CarryToZone position arrival tolerance
REPEATS = 3  # user 2026-10-16: unchanged same choice three times -> remove


def path_length(path):
    return sum(math.dist(a,b) for a,b in zip(path,path[1:]))


def shortcut(route, path, discs):
    """Greedy farthest visible path node; all edges use strict swept check."""
    if not path:return None
    out=[path[0]];i=0
    while i<len(path)-1:
        nxt=next((j for j in range(len(path)-1,i,-1) if route.segment(path[i],path[j],discs)[0]),None)
        if nxt is None:return None
        out.append(path[nxt]);i=nxt
    return out


class RouteProgress:
    def __init__(self, carry, *, complete=False):
        self.carry=carry;self.complete=complete;self.path=None;self.cursor=1
        self.target=None;self.events=[];self.last={};self.plans=0
        self.excluded=set();self.failures={};self.anchor={};self.selection=[]
        self.last_failure_t=-math.inf

    def select(self, now, grip):
        c=self.carry;r=c.reloc20_route;discs=c.obstacles.discs(now)
        cx,cy=c.region['center_m'];hx,hy=c.region['half_extents_m'];choices=[]
        self.selection=[]
        slots=[(cx+sx*max(0.,hx-.20),cy+sy*max(0.,hy-.20)) for sx,sy in ((0,0),(-1,0),(1,0),(0,-1),(0,1))]
        if not self.complete:slots=sorted(slots,key=lambda p:math.dist(c.loc.pose[:2],p))
        for slot in slots:
            key=tuple(slot);goal=(slot[0]-grip[0]-c.advance_m,slot[1]-grip[1])
            final=(goal[0]+c.advance_m,goal[1]);retreat=(final[0]-.15,final[1])
            row=dict(slot=slot,goal=goal,accepted=False,category='complete_plan',blocked_object='none',minimum_gap_m=None)
            if key in self.excluded:
                row.update(reason='unchanged_choice_removed_after_three',blocked_object='unchanged_route_candidate',gap_scope='not_applicable_progress_filter')
                self.selection.append(row);continue
            checks=[r.segment(a,b,discs) for a,b in ((goal,goal),(goal,final),(final,retreat))]
            if not all(ok for ok,_ in checks):
                row.update(min((x for ok,x in checks if not ok),key=lambda x:x['minimum_gap_m']));row['reason']='place_envelope_overlap'
                self.selection.append(row);continue
            path=r.plan(c.loc.pose[:2],goal,c.static['bounds_m'],discs)
            self.plans+=1
            if path is None:
                row.update(r.last);self.selection.append(row);continue
            path=shortcut(r,path,discs)
            if not path:
                row.update(reason='strict_shortcut_disconnected',blocked_object='loaded_route',gap_scope='no_strict_connecting_edge')
                self.selection.append(row);continue
            # Existing translational/turn command bounds. Planning estimate,
            # not measured throughput, not an acceptance/success threshold.
            angles=[math.atan2(b[1]-a[1],b[0]-a[0]) for a,b in zip(path,path[1:])]
            turns=sum(abs(wrap(b-a)) for a,b in zip([c.loc.pose[2]]+angles,angles+[0.]))
            cost=path_length(path)/.08+turns/.1
            context=min((r.segment(a,b,discs)[1] for a,b in zip(path,path[1:])),key=lambda x:x['minimum_gap_m'])
            row.update(accepted=True,reason='complete_plan_clear',path_length_m=path_length(path),estimated_command_s=cost,**{k:context[k] for k in ('blocked_object','minimum_gap_m','gap_scope')})
            self.selection.append(row);choices.append((cost,slot,goal,path))
            if not self.complete:break
        if not choices:
            self.path=None;self.target=None;return False
        _,c.slot,c.goal,self.path=min(choices,key=lambda x:x[0])
        c.path=self.path;self.cursor=1;self.target=self.path[1] if len(self.path)>1 else c.goal
        self.events.append(dict(t=now,event='route_selected',slot=c.slot,path=self.path,selection=self.selection.copy()))
        return True

    def failed(self, now, reason, context):
        # Inherited one-SIM-second planning opportunity; never wall time.
        if now-self.last_failure_t<1.-1e-8:return
        self.last_failure_t=now;c=self.carry;key=tuple(c.slot) if c.slot else None
        if key is None:return
        pose=tuple(c.loc.pose[:2]);old=self.anchor.get(key)
        if old is None or math.dist(pose,old)>=ARRIVAL_M:
            self.anchor[key]=pose;self.failures[key]=0
        self.failures[key]=self.failures.get(key,0)+1
        removed=self.failures[key]>=REPEATS
        if removed:self.excluded.add(key)
        self.events.append(dict(t=now,event='candidate_rejected' if removed else 'candidate_no_progress',reason=reason,
            unchanged_choices=self.failures[key],slot=key,category='route_progress',**context))
        self.path=None;self.target=None

    def step(self, now):
        c=self.carry;r=c.reloc20_route;pose=c.loc.pose;discs=c.obstacles.discs(now)
        if math.dist(pose[:2],c.goal)<=ARRIVAL_M:
            if abs(wrap(pose[2]))<=.04:
                c.arrived=now;return (0.,0.,0.),True,None
            from harness.reloc20_motion import guard
            return guard(c,(0.,0.,max(-.1,min(.1,-.6*wrap(pose[2])))),now),False,None
        if self.path is None:
            if not self.select(now,c.grip_xy):
                context=dict(c.reloc20_route.last)
                context={k:context.get(k) for k in ('blocked_object','minimum_gap_m','gap_scope')}
                context['blocked_object']=context['blocked_object'] or 'all_authored_slots'
                self.failed(now,'no_complete_route',context)
                if len(self.excluded)==5:return (0.,0.,0.),False,'reloc21_candidates_exhausted'
                return (0.,0.,0.),False,None
        while self.cursor<len(self.path)-1 and math.dist(pose[:2],self.path[self.cursor])<=ARRIVAL_M:
            self.cursor+=1
        self.target=self.path[self.cursor]
        ok,context=r.segment(pose[:2],self.target,discs)
        if not ok:
            self.failed(now,'persistent_edge_obstructed',{k:context[k] for k in ('blocked_object','minimum_gap_m','gap_scope')})
            return (0.,0.,0.),False,None
        self.last=dict(t=now,cursor=self.cursor,target=self.target,remaining_path_m=math.dist(pose[:2],self.target)+path_length(self.path[self.cursor:]),
            category='route_progress',reason='persistent_strict_route',**{k:context[k] for k in ('blocked_object','minimum_gap_m','gap_scope')})
        from harness.reloc20_motion import guard
        return guard(c,heading_forward(pose,self.target),now),False,None

    def record(self):
        return dict(option=OPTION,complete_plan=self.complete,last=self.last,plans=self.plans,
                    excluded_slots=sorted(self.excluded),events=self.events,selection=self.selection,
                    accepted_slots=sum(x['accepted'] for x in self.selection),slot_candidates=len(self.selection))


def install(carry, plan):
    for key in (OPTION,FULL):
        if type(plan.get(key,False)) is not bool:raise ValueError(key+' must be bool')
    if plan.get(FULL,False) and not plan.get(OPTION,False):raise ValueError(FULL+' requires '+OPTION)
    if plan.get(OPTION,False):
        if carry.reloc20_route is None or not carry.reloc20_heading:raise ValueError(OPTION+' requires loaded route and heading forward')
        carry.reloc21_nav=RouteProgress(carry,complete=plan.get(FULL,False))
