"""Evaluation-only telemetry. Never passed to a teacher, policy or transition."""
import numpy as np


def force_on_cargo(frame, local_force, cargo_is_geom2):
    # MuJoCo contact axes are rows; force points geom1 -> geom2.
    return (np.asarray(frame).reshape(3, 3).T @ np.asarray(local_force)[:3]
            * (1. if cargo_is_geom2 else -1.))


def collect(world, inst, roles):
    import mujoco
    m, d = world.model, world.data
    cargo = {m.geom(inst.geom(p.name)).id for p in inst.spec().parts if p.collision}
    fingers = {m.geom(f'{rid}__{side}_finger').id: rid for rid in roles for side in ('left', 'right')}
    loads = {rid: np.zeros(3) for rid in roles}
    other = np.zeros(3)
    force = np.zeros(6)
    contacts = []
    for i in range(d.ncon):
        c = d.contact[i]
        a, b = int(c.geom1), int(c.geom2)
        if (a in cargo) == (b in cargo):
            continue
        mujoco.mj_contactForce(m, d, i, force)
        f = force_on_cargo(c.frame, force, b in cargo)
        peer = a if b in cargo else b
        rid = fingers.get(peer)
        if rid is None:
            other += f
        else:
            loads[rid] += f
        contacts.append({'geom1': m.geom(a).name, 'geom2': m.geom(b).name,
                         'force_on_cargo_world_n': f.tolist(), 'position_world_m': c.pos.tolist()})
    joints = {}
    for rid in roles:
        joints[rid] = {}
        for name, joint in (('shoulder', 'shoulder'), ('elbow', 'elbow'), ('wrist', 'wrist_pitch')):
            aid = m.actuator(f'{rid}__servo_{name}').id
            jid = m.joint(f'{rid}__{joint}').id
            q = float(d.qpos[m.jnt_qposadr[jid]])
            joints[rid][name] = {'q_rad': q, 'qvel_rad_s': float(d.qvel[m.jnt_dofadr[jid]]),
                                'ctrl_rad': float(d.ctrl[aid]), 'ctrl_error_rad': float(d.ctrl[aid])-q,
                                'actuator_nm': float(d.actuator_force[aid]),
                                'limit_nm': float(m.actuator_forcerange[aid][1])}
    return {'scope': 'evaluation_only', 'joints': joints,
            'finger_force_on_cargo_world_n': {r: f.tolist() for r, f in loads.items()},
            'other_force_on_cargo_world_n': other.tolist(), 'contacts': contacts,
            'grip_world_m': {r: d.site(f'{r}__grip_site').xpos.tolist() for r in roles}}
