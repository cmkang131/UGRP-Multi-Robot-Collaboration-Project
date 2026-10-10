"""Default-off OwnRoute to cardinal S3 command plans. No map/simulator reader."""
import copy
import math
from types import SimpleNamespace

from harness import e2e_own_inputs as own
from harness.zone_study_contract import ContractViolation, digest
from harness.zone_s3_synchronized_carry import pulse_schedule
from harness.zone_s3_integer_carry import PulseWindows

OPTION = 'on_v1'


def compile_route(route, *, now, observed, profiles, option='off', source='own_map'):
    if option == 'off':
        return None
    if option != OPTION or source not in ('own_map', 'test_route_provider'):
        raise ContractViolation('UNKNOWN_OWN_ROUTE_ADAPTER')
    route = own.validate_route(route, 'r1', now, observed)
    if len(route['waypoints']) > 64:
        raise ContractViolation('OWN_ROUTE_TOO_LONG')
    points = [copy.deepcopy(route['waypoints'][0])]
    for a, b in zip(route['waypoints'], route['waypoints'][1:]):
        dx, dy = b[0]-a[0], b[1]-a[1]
        if math.hypot(dx, dy) < 1e-6 or abs(dx)>1e-8 and abs(dy)>1e-8:
            raise ContractViolation('S3_CARDINAL_NONZERO_LEG_REQUIRED')
        # Existing S3's <=0.85 m release/regrasp drift boundary.
        count = math.ceil(math.hypot(dx,dy)/.85)
        for i in range(1,count+1):points.append([a[0]+dx*i/count,a[1]+dy*i/count])
    if len(points)>64:raise ContractViolation('S3_SEGMENT_BUDGET_EXCEEDED')
    legs, turns, previous_heading = [], [], None
    for seg, (a, b) in enumerate(zip(points, points[1:])):
        dx, dy = b[0]-a[0], b[1]-a[1]
        if math.hypot(dx, dy) < 1e-6 or abs(dx) > 1e-8 and abs(dy) > 1e-8:
            raise ContractViolation('S3_CARDINAL_NONZERO_LEG_REQUIRED')
        heading = math.atan2(dy, dx)
        if previous_heading is not None:
            turn = math.atan2(math.sin(heading-previous_heading), math.cos(heading-previous_heading))
            if abs(turn) > 1e-8:
                turns.append(dict(at_seg=seg, route_turn_rad=turn, loaded_heading_turn_rad=0.,
                                  strategy='release_regrasp_then_axis_change'))
        plans = {}
        for rid in ('r1', 'r2'):
            ctl = SimpleNamespace(rid=rid, seg=seg, v3_plan={'route':points},
                                  claims={}, log=lambda *a, **k:None)
            schedule, duration = pulse_schedule(ctl, 0., profiles)
            windows = PulseWindows(schedule).windows
            plans[rid] = dict(windows=windows, duration_s=duration,
                              pulses=ctl.claims['segments'][0]['pulses'])
        legs.append(dict(seg=seg, start=list(a), end=list(b), distance_m=math.hypot(dx, dy),
                         axis='forward' if abs(dx)>1e-8 else 'left', plans=plans))
        previous_heading = heading
    result = dict(schema='ugrp.e2e_s3_plan.v1', source=source, frame=route['own_map']['frame'],
                  map_version=route['map_version'], route_hash=route['route_hash'],
                  B_rgb_sources=copy.deepcopy(route['B_rgb_sources']),
                  own_waypoints=copy.deepcopy(route['waypoints']), waypoints=points, legs=legs, turns=turns,
                  length_m=sum(l['distance_m'] for l in legs),
                  transport_admitted=False, research_result=False,
                  requires='received route approval and fresh per-grip-epoch GO/ACK')
    result['plan_hash'] = digest(result)
    return result


def plan_from_route(base_plan, compiled):
    """Explicit test-runtime shell only; no authored route survives this handoff."""
    if compiled['source'] != 'test_route_provider':
        raise ContractViolation('OWN_MAP_RUNTIME_NOT_CONNECTED_YET')
    plan = copy.deepcopy(base_plan)
    plan.update(route=copy.deepcopy(compiled['waypoints']),
                checkpoint_segments={'before_destination':len(compiled['legs'])-1},
                own_route=copy.deepcopy(compiled), registered_route_source='test_route_provider')
    return plan
