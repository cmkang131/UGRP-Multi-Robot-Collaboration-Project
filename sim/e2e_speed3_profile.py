"""Explicit E2E speed/physics cohorts; no historical result inheritance."""
import xml.etree.ElementTree as ET

PROFILES = {
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
