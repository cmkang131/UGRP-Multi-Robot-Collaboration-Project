"""Read-only MuJoCo constraint-space torque decomposition (post mj_step).

J^T efc_force is projected per constraint type using the official API. These
forces belong to the pre-integration state; callers must supply its qvel/time.
"""
import mujoco
import numpy as np


def snapshot(model, data, controller, pre_velocity, pre_time):
    dofs = np.array([model.jnt_dofadr[model.joint(f'{controller.robot_id}__wheel_{w}_joint').id]
                     for w in ('fl', 'fr', 'rl', 'rr')])
    terms = {}
    summed = np.zeros(model.nv)
    for kind in np.unique(data.efc_type):
        force = np.where(data.efc_type == kind, data.efc_force, 0.)
        projected = np.zeros(model.nv)
        mujoco.mj_mulJacTVec(model, data, projected, force)
        terms[mujoco.mjtConstraint(int(kind)).name] = projected[dofs].tolist()
        summed += projected
    inertia = np.zeros(model.nv)
    mujoco.mj_mulM(model, data, inertia, data.qacc)
    residual = (inertia + data.qfrc_bias - data.qfrc_passive - data.qfrc_actuator
                - data.qfrc_constraint - data.qfrc_applied)
    rows = np.flatnonzero((data.efc_type == mujoco.mjtConstraint.mjCNSTR_FRICTION_DOF)
                         & np.isin(data.efc_id, dofs))
    contacts = []
    for j in range(data.ncon):
        con = data.contact[j]
        names = [model.geom(int(g)).name for g in con.geom]
        if any(n.startswith(controller.robot_id+'__') and 'wheel_' in n for n in names):
            f = np.zeros(6)
            mujoco.mj_contactForce(model, data, j, f)
            contacts.append(dict(geoms=names, force_contact_frame=f.tolist(),
                                 frame=con.frame.tolist(), position=con.pos.tolist()))
    return dict(contact_reactions=contacts, t=pre_time, wheel_dofs=dofs.tolist(), pre_wheel_rad_s=np.asarray(pre_velocity)[dofs].tolist(),
        post_wheel_rad_s=data.qvel[dofs].tolist(), wheel_qacc=data.qacc[dofs].tolist(),
        actuator_force_nm=data.actuator_force[controller.wheel_act].tolist(),
        actuator_gear=model.actuator_gear[controller.wheel_act].tolist(),
        actuator_ctrl=data.ctrl[controller.wheel_act].tolist(),
        actuator_generalized_nm=data.qfrc_actuator[dofs].tolist(),
        passive_nm=data.qfrc_passive[dofs].tolist(), bias_nm=data.qfrc_bias[dofs].tolist(),
        inertia_nm=inertia[dofs].tolist(), constraint_nm=data.qfrc_constraint[dofs].tolist(),
        applied_nm=data.qfrc_applied[dofs].tolist(), constraint_terms_nm=terms,
        friction_limit_nm=model.dof_frictionloss[dofs].tolist(),
        friction_rows=[dict(dof=int(data.efc_id[j]), force_nm=float(data.efc_force[j]),
            limit_nm=float(data.efc_frictionloss[j]), velocity=float(data.efc_vel[j]),
            reference_acceleration=float(data.efc_aref[j]), regularizer=float(data.efc_R[j]),
            state=int(data.efc_state[j])) for j in rows],
        constraint_projection_error=float(np.max(np.abs(summed-data.qfrc_constraint))),
        wheel_balance_error_nm=float(np.max(np.abs(residual[dofs]))))
