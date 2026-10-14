"""Visible-lug grasp geometry for the demonstration teacher only, default off.

Spenrath & Kleeberger (2021), sec. 3.1: stroke, opposing surfaces and finger
collision checks before accepting a grasp. This is the rectangular-lug
specialization, not their full point-cloud sampler. Frozen crate/finger shape
dimensions are priors; the pose must come from a CURRENTLY visible lug.
No contact force, measured joint or hidden cargo pose is an input.
"""
import math

from harness import visual_arm as sdk
from harness.visual_arm_v3 import solve_grip_site_ik, tool_pose
from sim.grasp_act_teacher import local, wrap

LUG_LENGTH_M = .060
LUG_WIDTH_M = .040
OPEN_HALF_GAP_M = .035 - .0045
PAD_HALF_LENGTH_M = .00715
PAD_HALF_DEPTH_M = .0035
BODY_INSET_M = .100 - .070  # grasp point to the main box's end face
CLEARANCE_M = .002         # design clearance, not a success threshold


def check(angle_rad, pitch_rad):
    """Conservative open-jaw aperture and swept finger/body clearance.

    The whole lug footprint must fit the open aperture; this deliberately
    excludes corner/edge grasps. Both jaws then close across opposite side
    faces. The open position is the worst inward finger extent throughout
    closing. The fixed-XY descent is checked at every issued pose separately.
    """
    a = wrap(angle_rad)
    co, si = abs(math.cos(a)), abs(math.sin(a))
    width = LUG_WIDTH_M * co + LUG_LENGTH_M * si
    pad_horizontal = PAD_HALF_LENGTH_M * abs(math.cos(pitch_rad)) + PAD_HALF_DEPTH_M * abs(math.sin(pitch_rad))
    inward = (.035 + .0045) * si + pad_horizontal * co
    valid = (abs(a) < math.pi/2 and width + 2*CLEARANCE_M <= 2*OPEN_HALF_GAP_M
             and inward + CLEARANCE_M <= BODY_INSET_M)
    return {'valid': valid, 'axis_error_deg': math.degrees(a),
            'projected_lug_width_m': width, 'open_gap_m': 2*OPEN_HALF_GAP_M,
            'finger_inward_extent_m': inward, 'body_inset_m': BODY_INSET_M,
            'clearance_m': CLEARANCE_M}


def visible_grasp(world, rid, end, *, pose=None):
    """Check the existing hover/descent commands from a visible assigned lug."""
    if world['beam'] is None or world['visibility'][rid]['visible_probes'] < 5:
        return {'valid': False, 'reason': 'assigned_lug_not_visible'}
    pose = world['robots'][rid]['pose'] if pose is None else pose
    point = world['beam']['ends'][end]
    x, y = local(pose, point)
    axis = world['beam']['pose'][2] + (math.pi if end == 'blue' else 0.)
    try:
        grip = solve_grip_site_ik((x, y, point[2]))
        pitch = tool_pose(grip).pitch_deg
        samples = [solve_grip_site_ik((x, y, .095 + (point[2]-.095)*i/8),
                                    preferred_pitch_deg=pitch) for i in range(9)]
    except ValueError:
        return {'valid': False, 'reason': 'descent_ik_unreachable'}
    reports = []
    for pwm in samples:
        pan = math.radians((pwm[6]-sdk.BASE_CENTER)/sdk.PULSE_PER_DEGREE)
        reports.append(check(pose[2]+pan-axis, math.radians(tool_pose(pwm).pitch_deg)))
    return {'valid': all(r['valid'] for r in reports), 'samples': reports,
            'reason': 'rectangular_lug_stroke_and_finger_clearance',
            'input_source': 'current visible lug + known shape + planned PWM'}
