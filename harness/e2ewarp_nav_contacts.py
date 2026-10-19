"""Eval-only cross-robot contact ledger for ``--mode nav`` (never a controller input).

The navigation gate has no cargo, so the vendored backend's finger-force
channel is identically zero and the r3 report could only report a *geometric*
contact-possible interval (base centre distance < 0.181 m).  r4 step ② needs the
actual contact count and times, because contact is recorded as a failure cause
rather than an INVALID run.

This module reads the MJWarp contact buffer (``hooks.wd``) after each physics
step and returns the contacts whose two geoms belong to *different* execution
robots.  It is a pure post-step read: the navigation adapter, the LLM prompt,
the candidate list and the phase transition never see it, and it is written to
``contact-ledger.json`` in the run directory (evaluation sink only).

The MJWarp contact arrays are read defensively: a missing/renamed field returns
``None`` (recorded as ``contacts_available=false`` in the ledger) instead of
crashing the run or silently reporting zero contacts.
"""
from __future__ import annotations

import numpy as np

SCHEMA = 'ugrp.e2ewarp.nav_contact_ledger.v1'
ROBOT_PREFIXES = ('r1', 'r2', 'r3')


def geom_robot(name):
    """Execution robot prefix of a scene geom name, or None for world/scene geoms."""
    head = str(name or '').split('__', 1)[0]
    return head if head in ROBOT_PREFIXES else None


def base_box(model, robot):
    """Authored low base collision box (name/size/local position) for one robot."""
    want = str(robot) + '__base_lower_collision'
    for gid in range(int(model.ngeom)):
        if str(model.geom(gid).name) == want:
            return dict(geom=want, size=[float(v) for v in model.geom_size[gid]],
                        local_pos=[float(v) for v in model.geom_pos[gid]])
    return None


def read_contacts(hooks, world, *, robots, model=None):
    """Cross-robot contacts of one world after the last step, or None if unreadable.

    MJWarp stores contacts in a flat buffer with a ``worldid`` tag (the vendored
    evaluator kernel reads ``geom[i]``/``worldid[i]``/``nacon[0]``).  Every run
    in this task is ``nworld=1``, so the first ``nacon`` rows are this world's.
    """
    wd = getattr(hooks, 'wd', None)
    contact = getattr(wd, 'contact', None)
    nacon = getattr(wd, 'nacon', None)
    if contact is None or nacon is None or not hasattr(contact, 'geom'):
        return None
    model = model if model is not None else getattr(hooks, 'm', None)
    if model is None:
        return None
    try:
        counts = np.asarray(nacon.numpy()).reshape(-1)
        count = int(counts[world]) if counts.size > world else int(counts[0])
        geom = np.asarray(contact.geom.numpy())
        if geom.ndim != 2 or geom.shape[1] != 2:
            return None
        dist = np.asarray(contact.dist.numpy()).reshape(-1) if hasattr(contact, 'dist') else None
        worldid = (np.asarray(contact.worldid.numpy()).reshape(-1)
                   if hasattr(contact, 'worldid') else None)
    except (AttributeError, TypeError, ValueError):
        return None
    rows = []
    for i in range(min(count, geom.shape[0])):
        if worldid is not None and int(worldid[i]) != int(world):
            continue
        a, b = int(geom[i, 0]), int(geom[i, 1])
        name_a, name_b = str(model.geom(a).name), str(model.geom(b).name)
        robot_a, robot_b = geom_robot(name_a), geom_robot(name_b)
        if robot_a is None or robot_b is None or robot_a == robot_b:
            continue
        if robot_a not in robots or robot_b not in robots:
            continue
        rows.append(dict(geom_a=name_a, geom_b=name_b, robot_a=robot_a, robot_b=robot_b,
                         dist_m=(None if dist is None else round(float(dist[i]), 6))))
    return rows


def ledger(robots, *, base_boxes=None, note=''):
    """Empty ledger skeleton written by the runner before the rollout starts."""
    return dict(schema=SCHEMA, eval_only=True, robots=list(robots),
                contacts_available=None, unavailable_reason=None,
                base_boxes=base_boxes or {}, ticks=[], contact_ticks=0,
                contact_pairs_total=0, first_contact_s=None, last_contact_s=None,
                note=note)


def record(ledger_value, rows, now_s):
    """Append one tick's cross-robot contacts to the ledger (mutates and returns it)."""
    if rows is None:
        if ledger_value['contacts_available'] is None:
            ledger_value['contacts_available'] = False
            ledger_value['unavailable_reason'] = 'MJWarp contact buffer field missing'
        return ledger_value
    ledger_value['contacts_available'] = True
    if not rows:
        return ledger_value
    ledger_value['ticks'].append(dict(sim_s=round(float(now_s), 3), contacts=rows))
    ledger_value['contact_ticks'] += 1
    ledger_value['contact_pairs_total'] += len(rows)
    if ledger_value['first_contact_s'] is None:
        ledger_value['first_contact_s'] = round(float(now_s), 3)
    ledger_value['last_contact_s'] = round(float(now_s), 3)
    return ledger_value
