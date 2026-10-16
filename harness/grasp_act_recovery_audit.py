"""Evaluation-only ACT8 command-boundary diagnostics; never a teacher input."""
from contextlib import contextmanager
import json

import numpy as np


def snapshot(port, now, contact_force):
    world = port._world; model, data = world.model, world.data
    prefix = port.robot_id+'__'
    joints = [model.joint(prefix+f'wheel_{w}_joint') for w in ('fl','fr','rl','rr')]
    contacts = []
    for i in range(data.ncon):
        pair = data.contact[i]
        names = [model.geom(int(g)).name or '' for g in (pair.geom1,pair.geom2)]
        if not any(n.startswith(prefix) for n in names): continue
        force = np.zeros(6); contact_force(model,data,i,force)
        contacts.append({'geoms':names,'distance_m':float(pair.dist),'normal_force_N':float(force[0])})
    return {'t':now,'scope':'evaluation only, 10 Hz command boundary; transient sub-tick contacts may be missed',
        'base_xyz':list(map(float,port._robot.base_xyz())),
        'base_rpy':list(map(float,port._robot.base_rpy())),
        'wheel_qpos_rad':[float(data.qpos[j.qposadr[0]]) for j in joints],
        'wheel_qvel_rad_s':[float(data.qvel[j.dofadr[0]]) for j in joints],
        'contacts':contacts}


@contextmanager
def evaluation_hook(runner, stream, *, enabled=False):
    if not enabled:
        yield
        return
    # Only imported when the Linux runner has already entered the pinned scope.
    import mujoco
    original = runner.apply
    def audited(port, value, now, previous):
        result = original(port,value,now,previous)
        stream.write(json.dumps(snapshot(port,now,mujoco.mj_contactForce),allow_nan=False)+'\n')
        return result
    runner.apply = audited
    try: yield
    finally: runner.apply = original
