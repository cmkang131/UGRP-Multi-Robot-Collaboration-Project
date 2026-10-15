"""Bounded active perception from previously visible geometry and issued pose.

A retained bearing is a search hint, never fresh-clear evidence. Hazards are
retained while looking so memory expiry cannot authorize a translation.
"""
import math
from copy import deepcopy
from sim.grasp_act_teacher import local, wrap
from sim.grasp_act_visible_route import constraints, segment_free, free
from harness.static_keepouts import rect_distance


def observations(world, rid):
    return world['visibility'][rid].get('observations', {})


def remembered_blockers(world, rid, checked, folded):
    """Identify stale cargo/walls that actually rejected an IK-reachable goal."""
    radius = .13 if folded else .17
    extra = .17-radius
    goals = [r['goal'] for r in checked if r['reason'] == 'blocked_goal']
    result = {}
    for key, m in observations(world, rid).items():
        if m['seen_t'] >= world['t']-1e-8:
            continue
        if m['kind'] == 'cargo' and key != 'beam_1':
            padding = .005 if folded and m.get('top_z_bound_m', math.inf) <= .1 else .02+extra
            blocked = any(math.dist(g, m['xyz'][:2]) < radius+m['radius']+padding for g in goals)
        elif m['kind'] == 'wall':
            rect = (*m['xyz'][:2], *(h+extra for h in m['half_extents']), m['yaw'])
            blocked = any(rect_distance(g, rect) < radius for g in goals)
        else:
            continue
        if blocked:
            result[key] = deepcopy(m)
    return result


class ActiveReobserve:
    MAX_ENCOUNTERS = 2
    VIEW_S = .6
    RETREAT_S = .6
    LIMIT_S = 2.8

    def __init__(self):
        self.hints = {}
        self.active = None
        self.used = {'peer': 0, 'obstacle': 0}
        self.events = []
        self.pinned = {}

    def observe(self, world, rid):
        for key, m in observations(world, rid).items():
            if m['seen_t'] >= world['t']-1e-8:
                if m['kind'] == 'robot':
                    self.hints[key] = deepcopy(m)
                if key in self.pinned:
                    self.pinned[key] = deepcopy(m)

    def planning_world(self, world, rid):
        """Keep an unresolved rejected obstacle until a fresh measurement replaces it."""
        if not self.pinned:
            return world
        w = deepcopy(dict(world))
        current = observations(w, rid)
        for key, m in self.pinned.items():
            if key in current:
                continue
            if m['kind'] == 'cargo':
                w['objects'][key] = {'xy': m['xyz'][:2], 'radius': m['radius'],
                                     'top_z_bound_m': m['top_z_bound_m']}
            elif m['kind'] == 'wall':
                w['walls'].append((*m['xyz'][:2], *m['half_extents'], m['yaw']))
        return w

    def begin(self, kind, targets, world, teacher, now):
        if self.active or self.used[kind] >= self.MAX_ENCOUNTERS or not targets:
            return False
        self.used[kind] += 1
        if kind == 'obstacle':
            self.pinned.update(deepcopy(targets))
        snapshot=deepcopy(dict(world))
        for key,m in targets.items():
            if m['kind']=='robot' and key not in snapshot['robots']:
                snapshot['robots'][key]={'pose':[*m['xyz'][:2],m.get('yaw',0.)],
                                         'top_z_bound_m':m.get('top_z_bound_m',.32)}
        rad, ds, rs = constraints(snapshot, teacher.rid, teacher.folded_ready)
        self.active = {'kind': kind, 'targets': deepcopy(targets), 'start': now,
                       'pwm': dict(teacher.sink.pwm), 'world':snapshot, 'radius': rad, 'discs': ds, 'rects': rs,
                       'goal':teacher._geometry(world)[3],
                       'attempt': -1, 'retreat_start': None}
        self.events.append({'t': now, 'event': 'reobserve_start', 'kind': kind,
                            'encounter': self.used[kind], 'targets': deepcopy(targets),
                            'input': 'own visible history and issued-command pose only'})
        return True

    def finish(self, teacher, now, reason):
        a = self.active
        self.events.append({'t': now, 'event': 'reobserve_end', 'kind': a['kind'],
                            'reason': reason, 'elapsed_s': now-a['start']})
        self.active = None
        teacher.path = []; teacher.path_goal = None; teacher.next_plan = now
        teacher.peer_route = []; teacher.peer_route_next = now
        # No reset of progress, blocked_since, peer_wait_since, or episode clock.

    def step(self, world, teacher, now):
        from sim.grasp_act_gaze import slew
        from sim.grasp_act_visible_gaze import gaze_pose
        from harness.grasp_act_visible_world import command_delta
        a = self.active
        if a is None:
            return None
        rid = teacher.rid
        pose = world['robots'][rid]['pose']
        age = now-a['start']
        fresh = observations(world, rid)
        seen = {k for k in a['targets'] if k in fresh and fresh[k]['seen_t'] >= now-1e-8}
        if seen == set(a['targets']) and a['kind']=='peer':
            # Keep looking for the original 0.3s fresh-clear dwell. A single
            # glimpse must not release the wait or hand the gaze back too early.
            scene=deepcopy(dict(world))
            if scene['beam'] is None:scene['beam']=a['world']['beam']
            rad, ds, rs = constraints(scene, rid, teacher.folded_ready)
            goal=teacher._geometry(scene)[3]
            clear = free(goal, ds, rs, rad)
            teacher.peer_clear_since = (now if teacher.peer_clear_since is None else teacher.peer_clear_since) if clear else None
            if clear and now-teacher.peer_clear_since >= .3-1e-8:
                teacher.peer_wait_since=None;teacher.peer_wait_ids.clear();teacher.peer_clear_since=None
                teacher.progress.reset();teacher.peer_trigger.reset()
            else:
                seen=set()
        elif a['kind']=='peer':
            teacher.peer_clear_since=None
        if seen == set(a['targets']):
            self.events.append({'t': now, 'event': 'reobserve_measurements', 'kind': a['kind'],
                                'before': a['targets'], 'after': {k: fresh[k] for k in sorted(seen)}})
            self.finish(teacher, now, 'fresh_measurements_replan')
            return None
        if age >= self.LIMIT_S-1e-8:
            self.finish(teacher, now, 'bounded_reobserve_exhausted_replan')
            return teacher._hold(now)
        targets = [v for k, v in sorted(a['targets'].items()) if k not in seen]
        target = targets[min(int(age/self.VIEW_S), len(targets)-1)]
        x, y = local(pose, target['xyz'])
        z = (min(.20,target.get('top_z_bound_m',.32)/2) if target['kind']=='robot' else target['xyz'][2])
        view = gaze_pose((x, y, z), teacher.sink.pwm)
        before=({int(k):v for k,v in teacher.last_command['pwm'].items()}
                if teacher.last_command is not None else dict(teacher.sink.pwm))
        teacher.sink.pwm.update(slew(teacher.sink.pwm, view))
        teacher.arm.commanded.update(teacher.sink.pwm)
        attempt = min(3, int((age+1e-8)/self.VIEW_S))
        if attempt != a['attempt']:
            a['attempt'] = attempt
            self.events.append({'t': now, 'event': 'reobserve_attempt', 'kind': a['kind'],
                                'attempt': attempt, 'stage': 'view' if attempt < 3 else 'retreat',
                                'bearing_rad': math.atan2(y, x)})
        # Three bounded views: camera only, then body toward last bearing +/-30deg.
        if attempt < 3:
            offset = (0., -math.pi/6, math.pi/6)[attempt]
            turn = 0. if attempt == 0 else max(-.15, min(.15, .6*wrap(math.atan2(y, x)+offset)))
            value = teacher._continuous(now, 0., 0., turn)
        else:
            if a['retreat_start'] is None:
                a['retreat_start'] = (now, tuple(pose[:2]))
            t0, p0 = a['retreat_start']
            if now-t0 >= self.RETREAT_S-1e-8 or math.dist(pose[:2], p0) >= .06:
                self.finish(teacher, now, 'retreat_bounded_replan')
                return teacher._hold(now)
            value = teacher._continuous(now, -.05, 0., 0.)
        # Frozen hazards survive expiry. Current observations can only add checks.
        sets = [(a['radius'], a['discs'], a['rects'])]
        if world['beam'] is not None:
            sets.append(constraints(world, rid, teacher.folded_ready))
        dx, dy, da = command_delta(value, .1)
        co, si = math.cos(pose[2]), math.sin(pose[2])
        end = (pose[0]+co*dx-si*dy, pose[1]+si*dx+co*dy)
        x0, x1, y0, y1 = teacher.bounds
        if not (x0+a['radius'] <= end[0] <= x1-a['radius'] and y0+a['radius'] <= end[1] <= y1-a['radius']):
            safe = False
        else:
            safe = all(segment_free(pose[:2], end, ds, rs, r) for r, ds, rs in sets)
        from sim.grasp_act_pregrasp import issued_sweep_reason
        reason=issued_sweep_reason(a['world'],rid,pose,before,teacher.sink.pwm,(dx,dy,da))
        if reason is None:
            reason=issued_sweep_reason(world,rid,pose,before,teacher.sink.pwm,(dx,dy,da))
        if not safe or reason:
            teacher.sink.pwm.update(before);teacher.arm.commanded.update(before)
            self.finish(teacher, now, 'unsafe_motion_replan'+(':'+reason if reason else ''))
            return teacher._hold(now)
        return value
