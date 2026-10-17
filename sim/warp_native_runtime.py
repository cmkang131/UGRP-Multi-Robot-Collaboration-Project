"""Opt-in MJWarp runtime experiments, independent of frozen contact-v1 bytes.

Capacity is an allocation limit, never an accepted-contact threshold. The
official guide asks for the smallest non-overflowing measured allocation:
https://mujoco.readthedocs.io/en/latest/mjwarp/#batch-sizes
"""
import math

PROFILES = ('off', 'warp_upstream_plane_v1', 'warp_measured_capacity_v1')


def allocation(profile, reference, nworld, initial_ncon, initial_nefc):
    if profile not in PROFILES:
        raise ValueError('unknown runtime profile')
    if profile != 'warp_measured_capacity_v1':
        return None
    e = reference.get('every_step_envelope')
    if not e or not e.get('fixed_work_complete') or any(e.get('overflow', [])):
        raise ValueError('completed every-step native-v1 envelope required')
    if not e.get('source_states_sha256') or not e.get('source_result_sha256'):
        raise ValueError('envelope provenance required')
    # Observed P100, no guessed safety multiplier or power-of-two expansion.
    # nacon is a global contact buffer; njmax is per-world. Include the import
    # state because put_data must fit it before the first simulation step.
    nc = max(initial_ncon, math.ceil(e['max_nacon'] / e['nworld']))
    nf = max(initial_nefc, e['max_nefc'])
    return dict(naconmax=int(nc*nworld), njmax=int(nf),
                basis='every-physics-step native-v1 P100 + actual import; no margin; overflow rejects',
                envelope=e)


def collision(profile, model):
    if profile not in PROFILES:
        raise ValueError('unknown runtime profile')
    if profile == 'warp_upstream_plane_v1':
        # Run in a new process: no process-global monkeypatch to undo. Upstream
        # PLANE/MESH permits four contacts, C3.12's port selected up to three.
        return dict(mode=profile, implementation='unmodified pinned MJWarp plane_convex',
                    source='https://github.com/google-deepmind/mujoco_warp/blob/57b4692f4d3cdf4d27d916b4b8c4759ba36e9148/mujoco_warp/_src/collision_primitive.py')
    from scripts.simalt_collision_compat import install_legacy_plane
    return install_legacy_plane(model)
