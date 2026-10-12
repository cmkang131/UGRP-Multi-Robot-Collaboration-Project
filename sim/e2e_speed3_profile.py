"""Explicit E2E speed/physics cohorts; no historical result inheritance."""
import xml.etree.ElementTree as ET

PROFILES = {
    'adaptive_v1': dict(timestep_s=.002, integrator='implicitfast', iterations=80, observation_period_s=.4, contact_timestep_s=.00025),
    'dt1_v1': dict(timestep_s=.001, integrator='implicitfast', iterations=80, observation_period_s=.2),
    'dt2_v1': dict(timestep_s=.002, integrator='implicitfast', iterations=80, observation_period_s=.4),
}
REFERENCE = 'https://mujoco.readthedocs.io/en/3.6.0/computation/#numerical-integration'


def transform_xml(xml, profile):
    spec = PROFILES[profile]
    root = ET.fromstring(xml)
    option = root.find('option')
    option.set('timestep', str(spec['timestep_s']))
    option.set('integrator', spec['integrator'])
    option.set('iterations', str(spec['iterations']))
    return ET.tostring(root, encoding='unicode')


def apply_world(world, profile):
    import mujoco
    spec = PROFILES[profile]
    world.model.opt.timestep = spec['timestep_s']
    world.model.opt.integrator = mujoco.mjtIntegrator.mjINT_IMPLICITFAST
    world.model.opt.iterations = spec['iterations']
    return dict(profile=profile, **spec, noslip_iterations=int(world.model.opt.noslip_iterations))


def contact_command(action):
    """Only issued commands select the fine contact profile; no measured state."""
    from harness.active_camera import SEARCH
    return (action.get('kind')=='arm' and action.get('servo_id') in (1,3,4,5)
            and action.get('pulse') != SEARCH[action['servo_id']])


def enter_contact(backend, action):
    if backend.bundle['e2e_options'].get('speed3')!='adaptive_v1' or not contact_command(action):
        return False
    dt=PROFILES['adaptive_v1']['contact_timestep_s']
    if backend.dt == dt:return False
    old=backend.dt
    backend.world.model.opt.timestep=backend.dt=dt
    backend._clock_snap()
    backend._append('eval_only/speed3-physics-switch.jsonl',dict(t=backend.now,old_dt=old,new_dt=dt,
                    reason='issued_arm_leaves_search',action=action))
    return True
