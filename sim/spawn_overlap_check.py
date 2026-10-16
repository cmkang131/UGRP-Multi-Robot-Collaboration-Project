"""Opt-in setup admission, never a controller observation or action correction.

MuJoCo contact.dist is signed geometric separation (negative: penetration).
The zero tolerance is the geometric boundary, not a tuned solver tolerance:
margin/gap choose contact inclusion and solimp chooses force impedance; neither
permits an already intersecting t=0 spawn. We therefore do not subtract margin
or forgive solimp penetration. Floor support is explicitly excluded by name.
https://mujoco.readthedocs.io/en/stable/computation/#contact
"""
from __future__ import annotations

from collections import Counter
import math

OPTION = 'spawn_overlap_check_v1'
ALLOWED_DEPTH_M = 0.0


def cargo_owner(model, body_id, cargo_bodies):
    """Collision parts inherit their free cargo root even in nested models."""
    while body_id:
        name=model.body(body_id).name
        if name in cargo_bodies:
            return name
        body_id=int(model.body_parentid[body_id])
    return None


def classify(name, body_name, *, floor_geoms, cargo_bodies, wall_geoms):
    if name in floor_geoms:
        return 'floor'
    if body_name.split('__', 1)[0] in ('r1', 'r2', 'r3') and '__' in body_name:
        return 'robot'
    if body_name in cargo_bodies:
        return 'cargo'
    if name in wall_geoms:
        return 'wall'
    return 'other'


def assess(contacts, *, option='off'):
    """Pure admission from named contacts; default off does no measurement.

    All rejected points remain in the ledger, including repeated pair contacts.
    pair_count is distinct geometry pairs, never an episode success count.
    """
    if option not in ('off', OPTION):
        raise ValueError('UNKNOWN_SPAWN_OVERLAP_OPTION')
    if option == 'off':
        return dict(enabled=False, accepted=True, status='not_checked', rejections=[])
    rows=[]; tested=[]
    for point in contacts:
        a,b=point['classes']; dist=float(point['dist_m'])
        relevant=('robot' in (a,b) and 'floor' not in (a,b)) or sorted((a,b)) in (['cargo','cargo'],['cargo','wall'])
        if not relevant:
            continue
        tested.append(point)
        if not math.isfinite(dist) or dist < -ALLOWED_DEPTH_M:
            category='nonfinite_contact' if not math.isfinite(dist) else (
                'robot_nonfloor' if 'robot' in (a,b) else 'cargo_cargo' if a==b else 'cargo_wall')
            rows.append(dict(category=category,reason='nonfinite_signed_distance' if not math.isfinite(dist)
                else 't0_geometric_penetration',blocked_object=' <-> '.join(point['geoms']),
                geoms=point['geoms'],bodies=point['bodies'],minimum_gap_m=dist if math.isfinite(dist) else None,
                penetration_depth_m=-dist if math.isfinite(dist) else None,gap_status='measured' if math.isfinite(dist) else 'nonfinite',
                geom_margin_m=point.get('geom_margin_m'),solimp=point.get('solimp')))
    return dict(enabled=True,accepted=not rows,status='accepted' if not rows else 'rejected',
        allowed_depth_m=ALLOWED_DEPTH_M,contact_points_n=len(tested),rejected_contact_points_n=len(rows),
        pair_count=len({tuple(sorted(r['geoms'])) for r in rows}),reasons=dict(Counter(r['category'] for r in rows)),
        minimum_gap_m=min((p['dist_m'] for p in tested if math.isfinite(p['dist_m'])),default=None),
        gap_status='measured_contact_subset' if tested else 'no_relevant_contacts; noncontact_clearance_not_measured',
        rejections=rows)


def check(model, data, *, floor_geoms, cargo_bodies, wall_geoms, option='off'):
    """Run mj_forward only on caller-owned setup/evaluator data; no stepping.

    Native mj_forward is the requested setup contact test; it is not a CPU
    rollout. Explicit sets avoid treating ramps or every worldbody geom as floor.
    """
    if option == 'off':
        return assess([],option=option)
    if option != OPTION:
        raise ValueError('UNKNOWN_SPAWN_OVERLAP_OPTION')
    import mujoco
    mujoco.mj_forward(model,data)
    points=[]
    for contact in data.contact[:data.ncon]:
        ids=[int(contact.geom1),int(contact.geom2)]
        names=[model.geom(i).name or f'unnamed_geom_{i}' for i in ids]
        bodies=[model.body(int(model.geom_bodyid[i])).name or 'world' for i in ids]
        owners=[cargo_owner(model,int(model.geom_bodyid[i]),cargo_bodies) for i in ids]
        points.append(dict(geoms=names,bodies=bodies,dist_m=float(contact.dist),
            classes=[classify(n,owner or b,floor_geoms=floor_geoms,cargo_bodies=cargo_bodies,wall_geoms=wall_geoms)
                     for n,b,owner in zip(names,bodies,owners)],
            geom_margin_m=[float(model.geom_margin[i]) for i in ids],
            solimp=[model.geom_solimp[i].tolist() for i in ids]))
    result=assess(points,option=option)
    result.update(time_sim_s=float(data.time),all_contact_points_n=len(points),
        floor_geoms=sorted(floor_geoms),cargo_bodies=sorted(cargo_bodies),wall_geoms=sorted(wall_geoms),
        scope='native mj_forward contact subset at supplied setup; no CPU integration; no actor feedback')
    return result
