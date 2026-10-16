"""New execution defaults (2026-10-16); recorded legacy profiles remain explicit.

CPU native is a coordinator interpretation, not a claim of backend equivalence.
Options come from warpfit v1 (pinned vendor) and its original Newton/LS 80/50
scene, not newly tuned acceptance constants. No simulator import on this path.
"""
import xml.etree.ElementTree as ET
from sim.warp_native_contact import apply as native_xml, PROFILES

BUNDLE_ID = 'noslip-off-v445'
CPU_DEFAULT = 'cargo_native_v1'
WARP_DEFAULT = 'warp_native_contact_v1'
LEGACY = 'legacy_noslip10'
LEGACY_NAMES = (LEGACY, 'cargo_noslip_v1', 'baseline_noslip10')
CONTACT_PROFILES = (CPU_DEFAULT, WARP_DEFAULT, *LEGACY_NAMES)
NATIVE_OPTIONS = {**PROFILES[WARP_DEFAULT], 'solver': 'Newton',
                  'iterations': '80', 'ls_iterations': '50'}


def cargo_name(profile):
    if profile in LEGACY_NAMES:
        return 'cargo_noslip_v1'
    if profile in (CPU_DEFAULT, WARP_DEFAULT):
        return profile
    raise ValueError('unknown execution contact profile: '+str(profile))


def apply_xml(xml, profile=WARP_DEFAULT):
    """Native source options before compilation; legacy XML is byte-preserving."""
    if profile in LEGACY_NAMES:
        return xml
    cargo_name(profile)
    root = ET.fromstring(native_xml(xml, WARP_DEFAULT))
    root.find('option').attrib.update(NATIVE_OPTIONS)
    return ET.tostring(root, encoding='unicode')


def configure_model(model, profile=WARP_DEFAULT):
    """External frozen XML diagnostics: explicit native option override, no step."""
    if profile not in LEGACY_NAMES:
        cargo_name(profile)
        import mujoco
        for name, value in NATIVE_OPTIONS.items():
            enums = {'cone': mujoco.mjtCone, 'integrator': mujoco.mjtIntegrator,
                     'solver': mujoco.mjtSolver}
            if name in enums:
                prefix = {'cone': 'mjCONE_', 'integrator': 'mjINT_', 'solver': 'mjSOL_'}[name]
                value = getattr(enums[name], prefix+value.upper())
            else:
                value = float(value) if name == 'impratio' else int(value)
            setattr(model.opt, name, value)
    return assert_model_profile(model, profile)


def assert_model_profile(model, profile, active=None):
    """Check selected noslip against loaded C/Warp options, retaining weld OFF."""
    cargo_name(profile)
    expected = 10 if profile in LEGACY_NAMES else 0
    if int(model.opt.noslip_iterations) != expected:
        raise ValueError(f'{profile}: expected noslip_iterations={expected}, got {model.opt.noslip_iterations}')
    flags = active if active is not None else getattr(model, 'eq_active0', ())
    if hasattr(flags, 'numpy'):
        flags = flags.numpy().reshape(-1)
    if any(flags):
        raise ValueError('weld assistance must be OFF')
    return {'profile': profile, 'noslip_iterations': expected, 'execution_bundle_id': BUNDLE_ID}


def add_argument(parser, *, warp=False):
    parser.add_argument('--contact-profile', choices=CONTACT_PROFILES,
                        default=WARP_DEFAULT if warp else CPU_DEFAULT,
                        help='new executions: noslip 0; legacy_noslip10 only for recorded replay')


def build_world_with_contact(builder, profile, *args, **kwargs):
    """Adapt frozen builders inside their owned lane before any constructor step.

    Frozen builders import cargo.apply inside build_world. Scope the replacement
    to construction and restore it on exceptions; no frozen source is edited.
    """
    from sim import zone_cargo_contact as cargo
    original = cargo.apply
    def selected(xml, name):
        if profile in LEGACY_NAMES:
            return original(xml, 'cargo_noslip_v1')
        return apply_xml(original(xml, name), profile)
    cargo.apply = selected
    try:
        return builder(*args, **kwargs)
    finally:
        cargo.apply = original
