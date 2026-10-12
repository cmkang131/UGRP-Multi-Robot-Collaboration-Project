"""Evaluation-side synthetic stage initialization; never a control correction."""
import copy
import math

OPTION = 'public_stage_origin_v1'


def initialize(setup, case, public_start, option='off'):
    """Translate the reconstructed pair fixture before creating any controller.

    The authored route and task stay fixed. The beam and both carriers undergo
    the same rigid translation, preserving the six relative approach conditions.
    No running simulator state, PF prior or measured pose enters this function.
    """
    if option not in ('off', OPTION):
        raise ValueError('unregistered stage origin option')
    if option == 'off' or case == 'cyan':
        return setup
    if case != 'pair' or len(public_start) != 2 or not all(math.isfinite(x) for x in public_start):
        raise ValueError('finite public pair origin required')
    out = copy.deepcopy(setup)
    beam = out['truth']['items']['beam_1']
    origin = [beam['x'], beam['y']]
    delta = [a-b for a, b in zip(public_start, origin)]
    if not all(math.isfinite(x) for x in delta):
        raise ValueError('invalid committed stage fixture')
    beam['x'], beam['y'] = public_start
    for rid in ('r1', 'r2'):
        xyz = out['robots'][rid]['pose']['robot_xyz_m']
        xyz[:2] = [x+d for x, d in zip(xyz[:2], delta)]
    out['stage_origin_receipt'] = dict(option=option, eval_only_setup=True,
        source='committed reconstruction and public task start, before controller creation',
        original_beam_xy_m=origin, public_start_xy_m=list(public_start),
        rigid_translation_xy_m=delta, translated=['beam_1', 'r1', 'r2'],
        runtime_truth_feedback=False, controller_pose_prior=False)
    return out
