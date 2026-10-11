"""Opt-in meaningful set-downs, bounded HIGH continuation and own RGB fixes.

Nav2 separates waypoint traversal from waypoint tasks. Here the task is a
verified metric reobservation, never an unconditional release at every point.
Saved S4 measurements bound commanded travel; they are not live GT feedback.
"""
import copy
import math
import numpy as np
from harness import e2e_own_inputs as own
from harness.active_wall_mapping import compose, inverse
from harness.e2e_rgb_gate import features, geometric_match
from harness.zone_pair_highpose_dr_checkpoint import BUDGET_XY_M, BUDGET_YAW_RAD
from harness.zone_study_contract import ContractViolation

OPTION = 'on_v1'
# Minimum measured axial progress of 6 axial / 9 lateral longest pulse trains
# in the three completed s4live11 s601 dialogue runs. See audit/summary JSON.
CONTINUOUS_M = dict(forward=0.8277695513612384, left=0.8388003777717301)
PULSES = dict(forward=64, left=5)
RELOOK_TIMEOUT_S = 15.


def covariance_over(covariance):
    p = np.asarray(covariance, float)
    if p.shape != (3,3) or not np.isfinite(p).all() or np.linalg.eigvalsh(p).min() < -1e-12:
        raise ContractViolation('FINITE_OWN_COVARIANCE_REQUIRED')
    return (math.sqrt(max(0., float(np.linalg.eigvalsh(p[:2,:2]).max()))) > BUDGET_XY_M
            or math.sqrt(max(0., float(p[2,2]))) > BUDGET_YAW_RAD)


def boundary_reasons(compiled, first, seg, covariance):
    """Account for calibrated issued distance including ceil, not waypoint gap."""
    legs = compiled['legs']; current = legs[seg]
    reasons = list(compiled['relook_boundaries'].get(str(seg+1), []))
    if seg == len(legs)-1: reasons.append('final_placement')
    if covariance_over(covariance): reasons.append('covariance_limit')
    if seg+1 < len(legs):
        following = legs[seg+1]
        direction = lambda leg: np.sign(np.asarray(leg['end'])-leg['start']).tolist()
        if direction(current) != direction(following): reasons.append('unmeasured_axis_change')
        group = legs[first:seg+2]; axis = current['axis']
        if (sum(l['command_distance_m'] for l in group) > CONTINUOUS_M[axis]+1e-10 or
                sum(l['plans']['r1']['pulses'] for l in group) > PULSES[axis]):
            reasons.append('measured_continuous_limit')
    return list(dict.fromkeys(reasons))


def narrow_boundaries(route, points):
    """Bracket own-observed narrow wall crossings; no authored door geometry.

    A wall within 10 cm of the fixed pair envelope is a conservative narrow
    passage. Sample at 2 cm and bracket each contiguous interval by route
    points, so both before/after stops exist even inside a single short leg.
    A missing pre-door point at the route start means the initial look.
    """
    walls = route['own_map']['walls']
    narrow = []
    for a,b in zip(points,points[1:]):
        found = False
        for q in np.linspace(a,b,max(2,math.ceil(math.dist(a,b)/.02)+1)):
            lo,hi = q-np.array([.725,.30]),q+np.array([.725,.30])
            for w in walls:
                x,y = np.asarray(w['a']),np.asarray(w['b']); d=y-x
                low,high=0.,1.
                for k in (0,1):
                    if abs(d[k])<1e-12:
                        if not lo[k]<=x[k]<=hi[k]: low,high=1.,0.;break
                    else:
                        u,v=sorted(((lo[k]-x[k])/d[k],(hi[k]-x[k])/d[k]))
                        low,high=max(low,u),min(high,v)
                if low<=high: found=True;break
            if found: break
        narrow.append(found)
    result={}
    for i,value in enumerate(narrow):
        if value and (i==0 or not narrow[i-1]): result.setdefault(str(i),[]).append('before_narrow_passage')
        if value and (i==len(narrow)-1 or not narrow[i+1]): result.setdefault(str(i+1),[]).append('after_narrow_passage')
    return result


class OwnRGBRelook:
    """Consume GoalRoute's real receive/localize path, before graph insertion.

    A pinned prior own keyframe, ORB/RANSAC and three consistent CSM metric
    matches are required. The correction mutates the actual RBPF particle
    poses; correlated covariance is rotated, never reset or shrunk.
    """
    def __init__(self, goal, sink=None):
        self.goal, self.pending, self.receipt = goal, None, None
        goal.e2e_relook=self
        self.bound_plan_hash=None
        self.sink=sink
        self.history, self.current, self.events = {}, None, []
        receive, localize = goal.receive, goal._localize

        def receive_rgb(**kw):
            if kw['robot_id'] != goal.robot_id: raise ContractViolation('PEER_INPUT_FORBIDDEN')
            own.scan(kw['observation'])
            self.current = dict(ref=dict(robot_id=kw['robot_id'],frame_id=kw['frame_id'],
                t_sim=kw['t'],sha256=kw['frame_sha256']), features=features(kw['rgb']))
            result = receive(**kw)
            self.history[kw['frame_id']] = self.current
            # Retain only existing keyframes plus the current candidate.
            keep={n['frame_id'] for n in goal.graph.nodes[-64:]} | {kw['frame_id']}
            if self.pending and self.pending['node'] is not None:
                keep.add(goal.graph.nodes[self.pending['node']]['frame_id'])
            self.history={k:v for k,v in self.history.items() if k in keep}
            return result

        def fix(sample,t):
            if self.pending is None: return localize(sample,t)
            return self.observe(sample,t)

        goal.receive, goal._localize = receive_rgb, fix

    def emit(self,row):
        self.events.append(row)
        if self.sink is not None: self.sink(row)

    def request(self, now, *, seg, epoch):
        if self.pending is not None: return
        self.receipt=None
        self.bound_plan_hash=None
        candidates=[n for n in self.goal.graph.nodes if n['frame_id'] in self.history and n['t']<now]
        node=min(candidates,key=lambda n:math.dist(n['pose'][:2],self.goal.explorer.local_pose[:2])) if candidates else None
        self.pending=dict(t=now,seg=seg,epoch=epoch,node=None if node is None else node['id'],matches=[])
        self.emit(dict(event='e2e_relook_requested',t=now,seg=seg,epoch=epoch))

    def observe(self, sample, now):
        p=self.pending; cur=self.current
        if cur is None or p['node'] is None: return
        ref=cur['ref']
        own.rgb_ref(ref,self.goal.robot_id,now,[ref])
        if (ref['frame_id']!=sample['frame_id'] or ref['sha256']!=sample['frame_sha256'] or
                ref['t_sim']!=sample['t'] or not p['t']<sample['t']<=now or now-sample['t']>.25): return
        rows=p['matches']
        if rows and ref['frame_id']<=rows[-1]['ref']['frame_id']: return
        node=self.goal.graph.nodes[p['node']]
        visual=geometric_match(self.history[node['frame_id']]['features'],cur['features'])
        match=self.goal.graph.match(sample,p['node']) if visual['accepted'] else {'status':'rejected'}
        self.emit(dict(event='e2e_relook_rgb',t=now,seg=p['seg'],rgb=copy.deepcopy(ref),
                                visual=visual,metric_status=match['status'],node=p['node']))
        if match['status']!='accepted': rows.clear();return
        delta=compose(match['pose'],inverse(sample['pose']))
        if rows and (now-rows[-1]['ref']['t_sim']>.5 or
                np.linalg.norm(delta[:2]-rows[-1]['delta'][:2])>.05 or
                abs(math.atan2(math.sin(delta[2]-rows[-1]['delta'][2]),math.cos(delta[2]-rows[-1]['delta'][2])))>.05): rows.clear()
        rows.append(dict(ref=copy.deepcopy(ref),delta=delta.tolist()))
        if len(rows)<3 or now-rows[0]['ref']['t_sim']<.2-1e-8: return
        g=self.goal.explorer.memory.self_map
        before=list(g.odom.pose)
        g.poses=np.array([compose(delta,q) for q in g.poses])
        c,s=math.cos(delta[2]),math.sin(delta[2]);rotation=np.array([[c,-s,0],[s,c,0],[0,0,1]])
        g.pending_cov=rotation@g.pending_cov@rotation.T
        after=list(g.odom.pose)
        sample['pose'],sample['covariance']=after,self.goal.pose_covariance()
        self.goal.offsets.append(dict(t=now,delta=delta.tolist()))
        self.receipt=dict(event='e2e_pose_correction_applied',t=now,seg=p['seg'],epoch=p['epoch'],
            before=before,after=after,delta=delta.tolist(),rgb=[r['ref'] for r in rows[-3:]],
            node=p['node'],covariance_reset=False)
        self.emit(self.receipt);self.pending=None


def peer_route_after_relook(goal, report, *, own_map, now, observed, received_reports, profiles,
                           pulse_budget='off'):
    """r2 binds its corrected own pose to an actually delivered r1 route.

    Reuses the input contract's own-RGB common-beam transform; no shared world
    pose, private peer camera access or unreceived B report is admitted.
    """
    relook=getattr(goal,'e2e_relook',None)
    if goal.robot_id!='r2' or relook is None or relook.receipt is None:
        raise ContractViolation('APPLIED_R2_OWN_CORRECTION_REQUIRED')
    inputs=own.peer_s3_inputs(report,own_map=own_map,rid='r2',now=now,observed=observed,
                              received_reports=received_reports)
    if (not np.allclose(own_map['pose']['mean'],goal.explorer.local_pose,rtol=0,atol=1e-9) or
            report['beam_alignment']['own_rgb']['frame_id']<relook.receipt['rgb'][-1]['frame_id']):
        raise ContractViolation('CORRECTED_OWN_POSE_AND_FRESH_BEAM_REQUIRED')
    from harness.e2e_s3_route import compile_route
    route=report['route']
    compiled=compile_route(route,now=now,observed=route['own_map']['sources'],profiles=profiles,
        option='on_v1',source='own_map',pulse_budget=pulse_budget,setdown_only_when_relook=OPTION)
    relook.bound_plan_hash=compiled['plan_hash']
    relook.emit(dict(event='e2e_pose_correction_used_by_route',t=now,
                    route_hash=route['route_hash'],correction_frames=relook.receipt['rgb']))
    return dict(inputs=inputs,compiled=compiled)


def attach(ep, goal=None, *, agreement=None, option='off'):
    """After S3 adapters and before the final own-B gate; same adapter per robot.

    Host feeds each robot's GoalRoute.receive with its own RGB throughout S3.
    Missing feed/fix keeps the real cp_open/released handler closed and times
    out. After release, new epoch GO/ACK is still required at wait_carry.
    """
    if option=='off': return ep
    if option!=OPTION: raise ContractViolation('UNKNOWN_SETDOWN_ONLY_WHEN_RELOOK')
    ctl=ep.controller
    if (goal.robot_id!=ctl.rid or agreement is None or
            ctl.v3_plan.get('registered_route_source')!='own_map' or
            ctl.v3_plan['own_route'].get('setdown_only_when_relook')!=OPTION):
        raise ContractViolation('OWN_ROUTE_RELOOK_COMPOSITION_REQUIRED')
    def compiled():
        value=ctl.v3_plan['own_route']
        from harness.zone_study_contract import digest
        if (value.get('setdown_only_when_relook')!=OPTION or
                value['plan_hash']!=digest({k:v for k,v in value.items() if k!='plan_hash'})):
            raise ContractViolation('CURRENT_RELOOK_PLAN_REQUIRED')
        return value
    compiled()
    relook=OwnRGBRelook(goal,lambda row:ctl.log(ctl.rid,row['event'],row['t'],
                       **{k:v for k,v in row.items() if k not in ('event','t')}))
    state=dict(first=ctl.seg,epoch=ctl.grip_epoch,release=None,events=relook.events)
    ctl.e2e_setdown_relook=state
    carry,lower=ctl._wait_carry,ctl._wait_lower
    choice=ctl.carry_decision

    def reasons():
        if state['epoch']!=ctl.grip_epoch:
            state.update(first=ctl.seg,epoch=ctl.grip_epoch)
        return boundary_reasons(compiled(),state['first'],ctl.seg,goal.pose_covariance())

    def own_request(j,now,t_end=None):
        why=reasons()
        return dict(horizon_legs=[j],prediction=dict(over=bool(why)),named_checkpoints=why,
                    lead_hold_s=0.,dr_receipt_over=covariance_over(goal.pose_covariance()),request=bool(why))

    def carry_choice(value,now):
        if value=='set_down' and not reasons():
            return ctl._hook_verdict('carry_decision',value,now,'NO_RELOOK_TRIGGER')
        return choice(value,now)

    def wait_lower(now,idle):
        # The final B-boundary gate must be attached outside this wrapper so
        # it observes fresh RGB BEFORE the lower barrier can publish readiness.
        if (ctl.rid=='r1' and ctl.seg==len(ctl.segments)-1 and
                getattr(ctl,'e2e_final_rgb_gate',None) is not goal):
            return ctl.fail('FINAL_OWN_RGB_GATE_NOT_ATTACHED',now)
        return lower(now,idle)

    def released_handler(original):
        def released(now,idle):
            if not idle: return original(now,idle)
            key=(ctl.seg,ctl.grip_epoch)
            if state['release']!=key:
                state['release']=key
                state['released_at']=now
                state['released_route_hash']=compiled()['route_hash']
                agreement.key,agreement.votes=None,{}
                ctl.log(ctl.rid,'e2e_setdown_relook_started',now,seg=ctl.seg,reasons=reasons())
                # Existing fixed inspect posture, after floor/open completion.
                from harness.owncam_pair_beam_v2 import pose_of
                ctl.arm.queue({**pose_of('inspect'),6:ctl._issued()[6]},now,duration=.4,settle=.45)
                relook.request(ctl.arm.until,seg=ctl.seg,epoch=ctl.grip_epoch)
                return ctl.port.hold(now)
            receipt=relook.receipt
            if receipt is None:
                if now-state['released_at']>RELOOK_TIMEOUT_S:
                    return ctl.fail('OWN_RGB_POSITION_CORRECTION_TIMEOUT',now)
                return ctl.port.hold(now)
            if receipt['seg']!=ctl.seg or receipt['epoch']!=ctl.grip_epoch:
                raise ContractViolation('STALE_RELOOK_RECEIPT')
            ctl.log(ctl.rid,'e2e_setdown_relook_complete',now,**{k:v for k,v in receipt.items() if k not in ('event','t')})
            return original(now,idle)
        return released

    def wait_carry(now,idle):
        key=('order-5',ctl.v3_plan.get('agreement_route_hash'),ctl.grip_epoch,ctl.seg)
        if not agreement.ready or agreement.key!=key: return ctl.port.hold(now)
        # A post-release epoch cannot reuse its old GO/ACK. A HIGH continuation
        # retains the same grip epoch but requires the new segment key.
        if state['release'] and ctl.grip_epoch<=state['release'][1]: return ctl.port.hold(now)
        if state['release'] and (compiled()['route_hash']==state['released_route_hash'] or
                relook.bound_plan_hash!=compiled()['plan_hash']):
            # Applying a pose estimate is insufficient if the old static pulse
            # trajectory ignores it. Host must install the newly approved
            # OwnRoute generated from the corrected own map (and r2 alignment).
            ctl.log(ctl.rid,'e2e_corrected_route_required',now,seg=ctl.seg)
            return ctl.port.hold(now)
        if state['epoch']!=ctl.grip_epoch:
            state.update(first=ctl.seg,epoch=ctl.grip_epoch)
        leg=compiled()['legs'][ctl.seg]
        group=compiled()['legs'][state['first']:ctl.seg+1]
        direction=lambda row:np.sign(np.asarray(row['end'])-row['start']).tolist()
        if (sum(row['command_distance_m'] for row in group)>CONTINUOUS_M[leg['axis']]+1e-10 or
                sum(row['plans']['r1']['pulses'] for row in group)>PULSES[leg['axis']] or
                any(direction(row)!=direction(leg) for row in group)):
            return ctl.fail('CONTINUOUS_DISTANCE_UNMEASURED',now)
        if not ctl.held_by_command(): return ctl.fail('CONTINUATION_GRASP_COMMAND_REQUIRED',now)
        return carry(now,idle)

    ctl._own_request,ctl.carry_decision=own_request,carry_choice
    ctl._wait_carry,ctl._wait_lower=wait_carry,wait_lower
    ctl._cp_open=released_handler(ctl._cp_open)
    ctl._released=released_handler(ctl._released)
    return ep
