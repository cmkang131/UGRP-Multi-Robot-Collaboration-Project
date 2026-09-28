"""Static geometry budget arithmetic for the VIS4 preregistration draft."""
import math


def budgets():
    yaw = math.radians(3.)
    hy = .15*math.cos(yaw) + .20*math.sin(yaw)
    slot_y = .060 - (.020*math.cos(yaw)+.017*math.sin(yaw)) - .20*math.sin(yaw) - .010 - .005
    slot_x = .060 - (.017*math.cos(yaw)+.020*math.sin(yaw)) - .20*(1-math.cos(yaw)) - .010 - .005
    return {'yaw_cap_deg': 3., 'door_half_width_m': .25, 'loaded_envelope_half_y_at_3deg_m': hy,
            'door_lateral_remaining_m': .25-.02-hy-.01-.005,
            'door_lateral_gate_m': .05, 'door_joint_gate_m': .25-.15-.02-.01-.005,
            'slot_x_remaining_m': slot_x, 'slot_y_remaining_m': slot_y, 'slot_position_gate_m': .01,
            'existing_path_joint_budget_m': .020-.010-.005,
            'required_path_clearance_m': .060, 'path_joint_gate_m': .060-.010-.005,
            'path_translation_remaining_at_3deg_m': .060-.010-.005-2*.25*math.sin(yaw/2),
            'path_position_gate_m': .030}


def joint_path_error(position_error_m, yaw_error_rad):
    angle = abs((yaw_error_rad + math.pi) % (2*math.pi) - math.pi)
    return float(position_error_m) + 2*.25*math.sin(angle/2)


def joint_slot_extent(dx_m, dy_m, yaw_error_rad):
    """Upper bound of box extent from the nominal slot centre (fixed east heading)."""
    angle = abs((yaw_error_rad + math.pi) % (2*math.pi) - math.pi)
    c,s = abs(math.cos(angle)), abs(math.sin(angle))
    x = abs(dx_m) + .20*(1-math.cos(angle)) + .017*c + .020*s
    y = abs(dy_m) + .20*s + .020*c + .017*s
    return max(x,y)
