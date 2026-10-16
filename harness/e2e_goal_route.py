"""Default-off GoalRoute -> OwnRoute -> S3 provider and declaration hooks.

Only a robot-private GoalRoute/ObservedGrid and consumed RGB references enter.
No legacy authored runtime shell is reused for the own-map provider.
"""
import copy
import math
import numpy as np
from harness import e2e_own_inputs as own
from harness.e2e_covariance import inflate, OPTION as NEES
from harness.e2e_rgb_gate import ArrivalGate, OPTION as RGB
from harness.e2e_s3_route import compile_route, plan_from_route
from harness.e2e_dialogue import wire_route
from harness.goal_route_continuous import GoalRoute
from harness.own_map_navigation import footprint_clearance, PAIR_FOOTPRINT, astar
from harness.self_odom_grid import transform
from harness.active_wall_mapping import compose, inverse
from harness.zone_study_contract import ContractViolation, digest

OPTION = 'goal_route_v1'
SETDOWN = 'boundary_reobserve_v1'


def provider_plan(packet, *, agreement, now, observed, profiles):
    """S3 plan handoff after S4's actual received compact-route approval.

    Full private-map and compact wire digests are intentionally different.
    Recompute their binding rather than treating either as the other one.
    Carry still needs fresh epoch GO/ACK at pulse_authorizer.
    """
    route = own.validate_route(packet['route'], 'r1', now, observed)
    wire = wire_route(route)
    if (not agreement.approved or agreement.proposal is None or
            agreement.proposal[0] != wire['route_hash']):
        raise ContractViolation('RECEIVED_CURRENT_ROUTE_APPROVAL_REQUIRED')
    compiled = compile_route(route, now=now, observed=observed, profiles=profiles,
        option='on_v1', source='own_map', pulse_budget=packet['compiled'].get('pulse_budget', 'off'),
        setdown_only_when_relook=packet['compiled'].get('setdown_only_when_relook','off'))
    if packet['compiled'] != compiled:
        raise ContractViolation('COMPILED_OWN_ROUTE_MISMATCH')
    return {**plan_from_route(None, compiled), 'agreement_route_hash':wire['route_hash']}


def cardinal_path(points, clear):
    """Rectilinearize an own-grid path, checking every connector's swept envelope."""
    result = [list(points[0])]
    index = 0
    while index < len(points)-1:
        selected = None
        for j in range(len(points)-1, index, -1):
            a, b = result[-1], list(points[j])
            for corner in ([b[0], a[1]], [a[0], b[1]]):
                path = [a]
                for p in (corner, b):
                    if math.dist(path[-1], p) > 1e-8: path.append(p)
                if all(clear(x, y) for x, y in zip(path, path[1:])):
                    selected = (j, path[1:]); break
            if selected: break
        if selected is None: raise ContractViolation('NO_OBSERVED_CARDINAL_CORRIDOR')
        index, tail = selected; result.extend(tail)
    if len(result) < 2: raise ContractViolation('NONZERO_OWN_ROUTE_REQUIRED')
    return result


class IntegratedGoalRoute(GoalRoute):
    def receive(self, **kwargs):
        own.scan(kwargs['observation'])
        ref = dict(robot_id=kwargs['robot_id'], frame_id=kwargs['frame_id'],
                   t_sim=kwargs['t'], sha256=kwargs['frame_sha256'])
        own.rgb_ref(ref, self.robot_id, kwargs['t'], [ref])
        if self.e2e_observed and (ref['frame_id'] <= self.e2e_observed[-1]['frame_id'] or
                                  ref['t_sim'] <= self.e2e_observed[-1]['t_sim']):
            raise ContractViolation('NEW_OWN_RGB_REQUIRED')
        return super().receive(**kwargs)

    def pose_covariance(self):
        return inflate(super().pose_covariance(), option=self.e2e_options['covariance_inflation'],
                       profile=self.e2e_covariance_profile)

    def own_rgb_received(self, *, t, frame_id, rgb, servo, sample):
        ref = dict(robot_id=self.robot_id, frame_id=frame_id, t_sim=t, sha256=sample['frame_sha256'])
        own.rgb_ref(ref, self.robot_id, t, [ref])
        self.e2e_gate.observe(ref=ref, rgb=rgb, servo=servo, pose=sample['pose'], covariance=self.pose_covariance())
        self.e2e_observed.append(ref)
        seen = self.e2e_gate.current['boundary']
        if 'B' in self.entities and seen and math.dist(seen['center'], self.entities['B']['center_m']) <= .20:
            self.e2e_gate.remember_B()

    def arrival_evidence(self, name, t, frame_id, pose, evidence):
        if self.e2e_options['arrival_gate'] == 'off' or name != 'B': return evidence
        verdict = self.e2e_gate.verify('B', now=t, target=self.entities['B']['center_m'], near=evidence)
        self.event(t, 'e2e_B_declaration_gate', verdict=verdict)
        return verdict['accepted']

    def return_evidence(self, sample, near):
        if self.e2e_options['arrival_gate'] == 'off': return near
        # Explicit start-node geometric check, rather than a nearby arbitrary wall.
        matched = near and self.graph.match(sample, 0)['status'] == 'accepted'
        verdict = self.e2e_gate.verify('start', now=sample['t'], target=self.graph.nodes[0]['pose'][:2],
                                       near=near, geometry_confirmed=matched)
        self.event(sample['t'], 'e2e_return_declaration_gate', verdict=verdict)
        return verdict['accepted']

    def route_to_B(self, beam, *, now, profiles, pulse_budget='off', endpoint=None, endpoint_sources=None):
        if self.e2e_options['own_route'] == 'off': return None
        if self.robot_id != 'r1': raise ContractViolation('R1_GOAL_ROUTE_REQUIRED')
        own.closed(beam, ('rgb', 'pose_own_m'), 'OWN_BEAM')
        own.scan(beam); own.rgb_ref(beam['rgb'], 'r1', now, self.e2e_observed)
        own.numbers(beam['pose_own_m'], 3, 'OWN_BEAM_POSE')
        if now-beam['rgb']['t_sim'] > .25: raise ContractViolation('FRESH_OWN_BEAM_REQUIRED')
        diagnostic=getattr(self,'e2e_route_guard','off')!='off'
        if diagnostic:
            self.e2e_route_diagnostics=dict(t=now,beam_pose_own_m=copy.deepcopy(beam['pose_own_m']),beam_rgb=copy.deepcopy(beam['rgb']),sigma_xy_m=math.sqrt(float(np.linalg.eigvalsh(np.asarray(self.pose_covariance())[:2,:2]).max())),stage='beam_axes')
        from harness.e2e_beam_axis import error as axis_error
        beam_axis_error=axis_error(beam['pose_own_m'][2],getattr(self,'e2e_beam_axis','off'))
        if diagnostic:self.e2e_route_diagnostics['beam_axis_error_rad']=beam_axis_error
        carrier_axes=getattr(self,'e2e_carrier_axes','off')=='beam_v1'
        if beam_axis_error > math.radians(5) and not carrier_axes:
            raise ContractViolation('S3_OWN_AXES_BEAM_ALIGNMENT_REQUIRED')
        entity, reference = self.entities.get('B'), self.e2e_gate.references.get('B')
        if entity is None or entity['source'] != 'own' or reference is None:
            raise ContractViolation('OWN_RGB_REMEMBERED_B_REQUIRED')
        # Public API cannot smuggle an endpoint override. Reinspection below
        # supplies only the exact current verified boundary object.
        if endpoint is not None and (endpoint is not self.e2e_gate.current['boundary'] or not endpoint_sources):
            raise ContractViolation('VERIFIED_BOUNDARY_ONLY')
        target = entity['center_m'] if endpoint is None else endpoint['center']
        goal_sources = [reference['ref']] if endpoint_sources is None else endpoint_sources
        for ref in goal_sources: own.rgb_ref(ref, 'r1', now, self.e2e_observed)
        sources = copy.deepcopy(self.e2e_observed)
        grid, tf = self.explorer.grid, self.explorer.map_to_odom
        if grid.robot_id != 'r1': raise ContractViolation('PEER_GRID_FORBIDDEN')
        covariance = np.asarray(self.pose_covariance())
        margin = .02 + 3*math.sqrt(float(np.linalg.eigvalsh(covariance[:2, :2]).max()))
        _, allowed, clearance, lo = footprint_clearance(grid, PAIR_FOOTPRINT, margin,
                                                       yaw=float(tf[2])+beam['pose_own_m'][2])
        start = beam['pose_own_m'][:2]
        first, last = transform([start, target], tf)
        cells = astar(allowed, np.asarray(grid.cell(first))-lo, np.asarray(grid.cell(last))-lo,
                      grid.resolution, clearance)
        if diagnostic:
            from harness.e2e_route_guard import search as dev_search
            self.e2e_route_diagnostics.update(stage='grid_route',strict_margin_m=margin,B_own_m=list(target))
            allowed,clearance,lo,cells=dev_search(self,grid,tf,beam,first,last,margin,(allowed,clearance,lo,cells))
        if not cells: raise ContractViolation('OWN_GRID_ROUTE_UNAVAILABLE')
        path = [start] + transform([grid.point(np.asarray(c)+lo) for c in cells], inverse(tf)).tolist() + [list(target)]

        def clear(a, b):
            n = max(1, math.ceil(math.dist(a, b)/(grid.resolution/2)))
            for point in transform(np.linspace(a, b, n+1), tf):
                x, y = np.asarray(grid.cell(point))-lo
                if not (0 <= y < allowed.shape[0] and 0 <= x < allowed.shape[1] and allowed[y, x]): return False
            return True

        carrier_basis=None
        if carrier_axes:
            from harness.e2e_carrier_axes import basis,to_axes,from_axes
            carrier_basis=basis(beam,target)
            points=from_axes(cardinal_path(to_axes(path,carrier_basis),
                lambda a,b:clear(*from_axes([a,b],carrier_basis))),carrier_basis)
        else:points = cardinal_path(path, clear)
        # Occupied cell edges retain the actual wall RGB references. Empty or
        # unknown cells are not fabricated as observations of free space.
        refs = {r['frame_id']: r for r in sources}; walls = []
        for cell in grid.wall_frames:
            if grid.state(cell) != 1: continue
            ids = grid.wall_frames[cell]
            if any(i not in refs for i in ids): raise ContractViolation('UNOBSERVED_WALL_SOURCE')
            corner = np.asarray(cell)*grid.resolution
            corners = transform([corner, corner+[grid.resolution, 0], corner+grid.resolution,
                                 corner+[0, grid.resolution]], inverse(tf))
            for i in range(4): walls.append(dict(a=corners[i].tolist(), b=corners[(i+1)%4].tolist(),
                                                  sources=[refs[k] for k in sorted(ids)]))
        self.e2e_version += 1
        mapped = dict(robot_id='r1', frame='r1/own_start', map_version=self.e2e_version,
                      pose=dict(mean=np.asarray(self.explorer.local_pose, float).tolist(), covariance=covariance.tolist(), sources=[sources[-1]]),
                      walls=walls, goal=dict(label='B', sources=copy.deepcopy(goal_sources)), sources=sources)
        route = dict(schema=own.ROUTE_SCHEMA, robot_id='r1', frame_id=sources[-1]['frame_id'],
                     map_version=self.e2e_version, own_map=mapped, B_rgb_sources=copy.deepcopy(goal_sources), waypoints=points)
        if carrier_basis is not None:
            from harness.e2e_carrier_axes import ROUTE_SCHEMA
            route.update(schema=ROUTE_SCHEMA,carrier_basis=carrier_basis)
        route['route_hash'] = digest(route)
        compiled = compile_route(route, now=now, observed=sources, profiles=profiles, option='on_v1',
                                 source='own_map', pulse_budget=pulse_budget,
                                 setdown_only_when_relook=self.e2e_options['setdown_only_when_relook'])
        return dict(source='own_map', observed_coverage_complete=not getattr(self,'e2e_route_diagnostics',{}).get('would_stop_unknown',False), route=route, compiled=compiled,
                    inputs=own.s3_inputs(route, rid='r1', now=now, observed=sources),
                    proposal=dict(kind='OwnRoute', route=wire_route(route), source_message_id=None),
                    s3_plan={**plan_from_route(None, compiled), 'agreement_route_hash':wire_route(route)['route_hash']})

    def reobserve_setdown(self, current_packet, beam, *, now, profiles, agreement, pulse_budget='off'):
        if self.e2e_options['setdown_reobserve'] == 'off': return None
        own.closed(beam, ('rgb', 'pose_own_m'), 'OWN_BEAM')
        own.scan(beam); own.rgb_ref(beam['rgb'], 'r1', now, self.e2e_observed)
        own.numbers(beam['pose_own_m'], 3, 'OWN_BEAM_POSE')
        if now-beam['rgb']['t_sim'] > .25: raise ContractViolation('FRESH_OWN_BEAM_REQUIRED')
        verdict = self.e2e_gate.verify_boundary(now)
        if not verdict['accepted']:
            return dict(status='WAIT_OWN_RGB_BOUNDARY', allow_lower=False, pending_route=None)
        boundary = self.e2e_gate.current['boundary']
        if self.e2e_pending_setdown is not None and math.dist(
                boundary['center'], self.e2e_pending_setdown['boundary_center']) <= .02:
            return dict(status='REAPPROVAL_REQUIRED', allow_lower=False,
                        pending_route=self.e2e_pending_setdown['packet'])
        if math.dist(beam['pose_own_m'][:2], boundary['center']) > .02:
            packet = self.route_to_B(beam, now=now, profiles=profiles, pulse_budget=pulse_budget,
                                     endpoint=boundary, endpoint_sources=verdict['frames'])
        else:
            # Already at the corrected target: refresh provenance/approval but
            # do not manufacture a zero-length movement to get a new route hash.
            route = own.validate_route(current_packet['route'], 'r1', now, self.e2e_observed)
            if math.dist(route['waypoints'][-1], boundary['center']) > .02:
                raise ContractViolation('CURRENT_ROUTE_ENDPOINT_NOT_REACHED')
            self.e2e_version += 1
            route['map_version'] = route['own_map']['map_version'] = self.e2e_version
            route['frame_id'] = self.e2e_observed[-1]['frame_id']
            route['own_map']['sources'] = copy.deepcopy(self.e2e_observed)
            route['B_rgb_sources'] = route['own_map']['goal']['sources'] = copy.deepcopy(verdict['frames'])
            route['route_hash'] = digest({k:v for k,v in route.items() if k != 'route_hash'})
            compiled = compile_route(route, now=now, observed=self.e2e_observed, profiles=profiles,
                                     option='on_v1', source='own_map', pulse_budget=pulse_budget,
                                     setdown_only_when_relook=self.e2e_options['setdown_only_when_relook'])
            packet = dict(source='own_map', route=route, compiled=compiled,
                          inputs=own.s3_inputs(route, rid='r1', now=now, observed=self.e2e_observed),
                          proposal=dict(kind='OwnRoute', route=wire_route(route), source_message_id=None),
                          s3_plan={**plan_from_route(None, compiled), 'agreement_route_hash':wire_route(route)['route_hash']})
        # Every replan changes the route digest; old claim/GO/ACK cannot survive.
        previous_epoch = agreement.key[2] if agreement.key else 0
        agreement.proposal, agreement.approved, agreement.key, agreement.votes = None, False, None, {}
        self.e2e_pending_setdown = dict(packet=packet, boundary_center=boundary['center'], previous_epoch=previous_epoch)
        return dict(status='REAPPROVAL_REQUIRED', allow_lower=False, pending_route=packet)

    def route_after_relook(self, beam, *, now, profiles, agreement, pulse_budget='off'):
        """Consume an actually applied own fix in the next S3 pulse trajectory.

        The host obtains beam center from the same robot's calibrated RGB and
        installs provider_plan only after the new compact route is received
        and approved. r2 separately aligns that delivered route to its own map.
        """
        relook=getattr(self,'e2e_relook',None)
        receipt=None if relook is None else relook.receipt
        if (receipt is None or self.e2e_options['setdown_only_when_relook']=='off' or
                beam['rgb']['frame_id']<receipt['rgb'][-1]['frame_id']):
            raise ContractViolation('APPLIED_OWN_RGB_CORRECTION_REQUIRED')
        packet=self.route_to_B(beam,now=now,profiles=profiles,pulse_budget=pulse_budget)
        relook.bound_plan_hash=packet['compiled']['plan_hash']
        self.event(now,'e2e_pose_correction_used_by_route',route_hash=packet['route']['route_hash'],
                   correction_frames=copy.deepcopy(receipt['rgb']),map_version=packet['route']['map_version'])
        agreement.proposal,agreement.approved,agreement.key,agreement.votes=None,False,None,{}
        return packet

    def setdown_ready(self, footprint, *, now, agreement, order_id, grip_epoch, seg):
        """No declaration/actuation from geometry alone: fresh revised agreement is mandatory."""
        if self.e2e_options['setdown_reobserve'] == 'off': return True
        pending = self.e2e_pending_setdown
        if pending is None or not agreement.ready: return False
        if seg != len(pending['packet']['compiled']['legs'])-1: return False
        key = (order_id, wire_route(pending['packet']['route'])['route_hash'], grip_epoch, seg)
        if agreement.key != key or grip_epoch <= pending['previous_epoch']: return False
        own.closed(footprint, ('rgb', 'polygon_own_m'), 'OWN_BEAM_FOOTPRINT')
        own.scan(footprint); own.rgb_ref(footprint['rgb'], 'r1', now, self.e2e_observed)
        current = self.e2e_gate.current
        if current is None or footprint['rgb'] != current['ref'] or now-current['ref']['t_sim'] > .25: return False
        if not self.e2e_gate.verify_boundary(now)['accepted']: return False
        boundary = current['boundary']
        if math.dist(boundary['center'], pending['boundary_center']) > .02: return False
        polygon = np.asarray(footprint['polygon_own_m'], float)
        if polygon.shape != (4, 2) or not np.isfinite(polygon).all():
            raise ContractViolation('OWN_BEAM_FOUR_CORNERS_REQUIRED')
        sigma = math.sqrt(float(np.linalg.eigvalsh(np.asarray(self.pose_covariance())[:2,:2]).max()))
        import cv2
        contour = np.asarray(boundary['polygon'], np.float32)
        return all(cv2.pointPolygonTest(contour, tuple(map(float, p)), True) >= .01+3*sigma for p in polygon)


def attach(controller, *, own_route='off', arrival_gate='off', covariance_inflation='off',
           covariance_profile=None, setdown_reobserve='off', setdown_only_when_relook='off'):
    options = dict(own_route=own_route, arrival_gate=arrival_gate, covariance_inflation=covariance_inflation,
                   setdown_reobserve=setdown_reobserve,setdown_only_when_relook=setdown_only_when_relook)
    for key, allowed in (('own_route', OPTION), ('arrival_gate', RGB), ('covariance_inflation', NEES),
                         ('setdown_reobserve', SETDOWN), ('setdown_only_when_relook','on_v1')):
        if options[key] not in ('off', allowed): raise ContractViolation('UNKNOWN_E2E_' + key.upper())
    if all(v == 'off' for v in options.values()): return controller
    if type(controller) is not GoalRoute: raise ContractViolation('EXACT_GOAL_ROUTE_ADAPTER_REQUIRED')
    if own_route != 'off' and controller.robot_id != 'r1': raise ContractViolation('R1_GOAL_ROUTE_REQUIRED')
    if setdown_reobserve != 'off' and own_route == 'off': raise ContractViolation('SETDOWN_REQUIRES_OWN_ROUTE')
    if setdown_only_when_relook != 'off' and controller.robot_id == 'r1' and own_route == 'off':
        raise ContractViolation('RELOOK_REQUIRES_OWN_ROUTE_PROVIDER')
    controller.__class__ = IntegratedGoalRoute
    controller.e2e_options = options; controller.e2e_covariance_profile = copy.deepcopy(covariance_profile)
    controller.e2e_observed = []; controller.e2e_version = 0
    controller.e2e_pending_setdown = None
    controller.e2e_gate = ArrivalGate(controller.robot_id, option=RGB)
    if covariance_inflation != 'off': controller.pose_covariance()  # fail before accepting a frame
    return controller


def attach_setdown_gate(ep, controller, *, agreement, observation, option='off'):
    """Connect the final native S3 lower barrier to current own-RGB evidence.

    observation(now) returns own measured footprint + the current protocol key.
    Reinspection/replanning is supplied through reobserve_setdown and the normal
    S4 proposal callback. A missing/rejected frame produces a hold, never lower.
    """
    if option == 'off': return ep
    if option != SETDOWN or controller.e2e_options['setdown_reobserve'] != SETDOWN:
        raise ContractViolation('EXPLICIT_SETDOWN_REOBSERVATION_REQUIRED')
    ctl, lower = ep.controller, ep.controller._wait_lower
    if ctl.rid != 'r1': raise ContractViolation('R1_PRIVATE_RGB_GATE_REQUIRED')
    def wait_lower(now, idle):
        if ctl.seg == len(ctl.v3_plan['route'])-2:
            data = observation(now)
            pending = controller.e2e_pending_setdown
            installed_hash = ctl.v3_plan.get('own_route', {}).get('route_hash')
            if (pending is None or installed_hash != pending['packet']['route']['route_hash'] or
                    data is None or not controller.setdown_ready(now=now, agreement=agreement, **data)):
                ctl.port.hold(now)
                ctl.log(ctl.rid, 'e2e_setdown_reobserve_wait', now, seg=ctl.seg)
                return
        return lower(now, idle)
    ctl._wait_lower = wait_lower
    ctl.e2e_final_rgb_gate = controller
    return ep
