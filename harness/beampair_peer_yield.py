"""Opt-in, asymmetric approach reservation from the currently visible beam.

Silver (2005) motivates reserving another agent's destination before planning;
PIBT (2019) motivates breaking symmetric contention with an ordered priority.
This local geometric reservation is neither full algorithm and has no MAPF
completeness claim. No peer trajectory, messages or hidden pose are required.
"""
import math

MODE = 'beampair_peer_yield_v1'


def escape_anchors(start, disc, bounds, *, radius=.13, grid=.05):
    """Extend the existing exact_start_path 5cm lattice to the reservation.

    R1 8318728 starts 23.5cm inside the added reservation: neither the
    original 20cm nearest_free search nor its 3x3 A* anchors can leave it.
    Triangle inequality bounds the circle by clearance+centre distance;
    one lattice cell covers snapping. This is a finite check count, not a
    new fitted tolerance, timeout or smaller clearance.
    """
    reach=math.ceil((disc[2]+radius+math.dist(start,disc[:2]))/grid)+1
    ix,iy=round((start[0]-bounds[0])/grid),round((start[1]-bounds[2])/grid)
    points=[(bounds[0]+(ix+i)*grid,bounds[2]+(iy+j)*grid)
            for i in range(-reach,reach+1) for j in range(-reach,reach+1)]
    return sorted(points,key=lambda p:(math.dist(start,p),p))


def constraint_names(teacher,world,discs,rects):
    names=[r for r in world['robots'] if r!=teacher.rid]
    names += [k for k in world['objects'] if k!='beam_1']+['beam_1']*5+['reserved:teal_stance']
    if len(names)!=len(discs):raise ValueError('reservation constraint identity mismatch')
    walls=[k for k,m in world['visibility'][teacher.rid].get('observations',{}).items() if m['kind']=='wall']
    return [(name,[disc],[]) for name,disc in zip(names,discs)]+[
        (walls[i] if i<len(walls) else f'wall_layer_rect_{i}',[],[r]) for i,r in enumerate(rects)]


def signed_gap(point,discs,rects,radius,*,start=None):
    from harness.static_keepouts import rect_distance
    if discs:
        x,y,r=discs[0]
        if start is None:return math.dist(point,(x,y))-r-radius
        dx,dy=point[0]-start[0],point[1]-start[1];norm=dx*dx+dy*dy
        u=max(0.,min(1.,((x-start[0])*dx+(y-start[1])*dy)/norm)) if norm else 0.
        return math.hypot(start[0]+u*dx-x,start[1]+u*dy-y)-r-radius
    if start is None:return rect_distance(point,rects[0])-radius
    # Same 1mm sampling as the unchanged native strict_segment predicate.
    n=max(1,math.ceil(math.dist(start,point)/.001))
    return min(rect_distance((start[0]+(point[0]-start[0])*i/n,start[1]+(point[1]-start[1])*i/n),rects[0])-radius for i in range(n+1))


class ReservationNavigation:
    """One checked virtual-start connector, then the original finite A*."""
    def __init__(self,nav,teacher,world,disc,cs):
        self.nav=nav;self.teacher=teacher;self.world=world;self.disc=disc;self.cs=cs

    def __getattr__(self,name):return getattr(self.nav,name)

    def plan_path(self,start,goal,bounds,discs,*,rects=(),radius=.13):
        path=self.nav.plan_path(start,goal,bounds,discs,rects=rects,radius=radius)
        if path or math.dist(start,self.disc[:2])>=self.disc[2]+radius:return path
        candidates=[];anchor=None
        names=constraint_names(self.teacher,self.world,discs,rects)
        points=escape_anchors(start,self.disc,bounds,radius=radius)
        excluded=self.teacher.peer_yield_failed_anchors
        for p in points:
            if p in excluded:continue
            row=dict(point=list(p),reason='connector_feasible',reason_category='connector_feasible',
                blocked_object='none:all_checks_passed',min_gap_m=None,gap_scope='native point and continuous connector checks')
            candidates.append(row)
            if not (bounds[0]<=p[0]<=bounds[1] and bounds[2]<=p[1]<=bounds[3]):
                row.update(reason='outside_bounds',reason_category='outside_bounds',blocked_object='planning_bounds',
                    min_gap_m=min(p[0]-bounds[0],bounds[1]-p[0],p[1]-bounds[2],bounds[3]-p[1]));continue
            point_ok=self.nav.free(p,discs,rects,radius)
            edge_ok=point_ok and self.nav.segment_free(start,p,discs,rects,radius)
            if not edge_ok:
                bad=[(name,ds,rs) for name,ds,rs in names if not (
                    self.nav.free(p,ds,rs,radius) if not point_ok else self.nav.segment_free(start,p,ds,rs,radius))]
                if not bad:raise ValueError('native connector rejection missing named constraint')
                name,ds,rs=min(bad,key=lambda x:signed_gap(p,x[1],x[2],radius,start=None if not point_ok else start))
                row.update(reason='endpoint_blocked' if not point_ok else 'connector_blocked',
                    reason_category='reservation_goal' if name.startswith('reserved:') else 'visible_constraint',
                    blocked_object=name,min_gap_m=signed_gap(p,ds,rs,radius,start=None if not point_ok else start))
                continue
            row['min_gap_m']=min(signed_gap(p,ds,rs,radius) for _,ds,rs in names)
            anchor=p;break
        rest=self.nav.plan_path(anchor,goal,bounds,discs,rects=rects,radius=radius) if anchor is not None else None
        if anchor is not None and not rest:excluded.add(anchor)
        self.teacher.peer_yield_connector_log.append(dict(t=self.world['t'],event='reservation_escape_connector',
            reason_category='checked_virtual_start' if rest else 'no_checked_virtual_start_route',
            blocked_object='reserved:teal_stance',min_gap_m=math.dist(start,self.disc[:2])-self.disc[2]-radius,
            gap_scope='added task reservation; actual keepouts unchanged',grid_m=.05,
            grid_population_N=len(points),checked_N=len(candidates),candidates=candidates,
            rest_path_found=bool(rest),anchor=list(anchor) if anchor is not None else None))
        return [tuple(start),*rest] if rest else None


def reserved_teal_stance(world, rid, end, folded, station):
    # Blue yields the teal destination throughout approach. The ordered end
    # labels already come from the authorized task, not a live peer state.
    # Only a CURRENT admitted own-camera band may supply beam geometry.
    if (end != 'blue' or world['beam'] is None
            or world['visibility'][rid]['visible_probes'] < 5):
        return None
    g = world['beam']['ends']['teal']
    a = world['beam']['pose'][2]
    # station is the pinned nominal grasp stance (STATION_M), not a new fit.
    # Match visible_route.constraints' unchanged peer exclusion exactly:
    # own radius .13 folded/.17 unfolded + peer .17 + folding compensation.
    radius = .13 if folded else .17
    return (g[0]-station*math.cos(a), g[1]-station*math.sin(a),
            .17+(.17-radius))


class PeerYieldMixin:
    def _navigation(self,world):
        nav=super()._navigation(world)
        if (self.peer_yield=='off' or self.phase in ('pick','complete')
                or not getattr(nav,'true_start',False) or getattr(nav,'rectangle',False)):return nav
        from sim.grasp_act_teacher import STATION_M
        disc=reserved_teal_stance(world,self.rid,self.end,self.folded_ready,STATION_M)
        if disc is None:return nav
        return ReservationNavigation(nav,self,world,disc,self._constraints(world))

    def _constraints(self, world):
        cs = super()._constraints(world)
        if self.peer_yield == 'off' or self.phase in ('pick', 'complete'):
            return cs
        from sim.grasp_act_teacher import STATION_M
        disc = reserved_teal_stance(world, self.rid, self.end, self.folded_ready, STATION_M)
        if disc is None:
            return cs
        radius, discs, rects = cs
        # A fixed task-space reservation must survive dynamic peer TTL expiry.
        # It is an extra plain disc, never a removed/expired physical keepout.
        now = world['t']
        if not self.peer_yield_log or self.peer_yield_log[-1]['t'] != now:
            gap = math.dist(world['robots'][self.rid]['pose'][:2], disc[:2])-disc[2]-radius
            self.peer_yield_log.append(dict(t=now, event='reserved_teal_destination',
                reason_category='peer_destination_reservation', blocked_object='reserved:teal_stance',
                min_gap_m=gap, blocked=gap < 0., reserved_disc=list(disc),
                gap_scope='own visible band + known rigid beam + original peer exclusion; not measured peer pose'))
        return radius, [*discs, disc], rects

    def diagnostic(self):
        d = super().diagnostic()
        d.update(peer_yield=self.peer_yield, peer_yield_log=self.peer_yield_log,
                 peer_yield_connector_log=self.peer_yield_connector_log)
        return d
