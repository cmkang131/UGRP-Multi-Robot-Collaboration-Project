"""Explicit synthetic route payload; never called an observed own map.

RGB hashes attest the frame bytes only. Goal/pose/waypoints are TEST FIXTURES,
not an inference from those frames. The normal autonomous adapter stays off.
"""
import copy
from harness import e2e_own_inputs as own
from harness.zone_study_contract import digest

WAYPOINTS = [[1.275,.05],[4.6,.05],[4.6,-2.1]]


def provide(rgb_ref):
    sources = [copy.deepcopy(rgb_ref)]
    mapped = dict(robot_id='r1', frame='r1/own_start', map_version=1,
                  pose=dict(mean=[0.,0.,0.], covariance=[[.01,0.,0.],[0.,.01,0.],[0.,0.,.01]],sources=sources),
                  walls=[], goal=dict(label='B',sources=sources), sources=sources)
    route = dict(schema=own.ROUTE_SCHEMA, robot_id='r1', frame_id=rgb_ref['frame_id'],
                 map_version=1, own_map=mapped, B_rgb_sources=sources, waypoints=copy.deepcopy(WAYPOINTS))
    route['route_hash'] = digest(route)
    return dict(source='test_route_provider', synthetic=True, E2E_success_eligible=False,
                coordinate_frame='synthetic east/north frame; diagnostic legacy runtime only', route=route)
