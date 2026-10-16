"""Own-grid route candidates; the task model selects, the compiler validates."""
import copy,math
from harness.zone_study_contract import digest


def alternatives(packet, paths, *, now, observed, profiles):
    from harness.e2e_s3_route import compile_route,plan_from_route
    from harness.e2e_dialogue import wire_route
    from harness.e2e_own_inputs import s3_inputs
    result={};seen=set()
    for name,points in paths.items():
        if tuple(map(tuple,points)) in seen:continue
        seen.add(tuple(map(tuple,points)))
        p=copy.deepcopy(packet);r=p['route'];r['waypoints']=copy.deepcopy(points)
        r['route_hash']=digest({k:v for k,v in r.items() if k!='route_hash'})
        p['compiled']=compile_route(r,now=now,observed=observed,profiles=profiles,option='on_v1',source='own_map',
            pulse_budget=packet['compiled'].get('pulse_budget','off'),setdown_only_when_relook=packet['compiled'].get('setdown_only_when_relook','off'))
        p['inputs']=s3_inputs(r,rid='r1',now=now,observed=observed)
        p['proposal']=dict(kind='OwnRoute',route=wire_route(r),source_message_id=None)
        p['s3_plan']={**plan_from_route(None,p['compiled']),'agreement_route_hash':wire_route(r)['route_hash']}
        result[name]=p
    return result


def preview(packet):
    points=packet['route']['waypoints'];distance=sum(math.dist(a,b) for a,b in zip(points,points[1:]))
    return dict(distance_m=distance,expected_s=distance/.1,route_waypoints=copy.deepcopy(points),
        route_hash=packet['route']['route_hash'],source='own RGB map plus registered pulse estimate; time is uncertain')
