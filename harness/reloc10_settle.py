"""Adapter from angular error to the existing calibrated safe pulse lattice."""
import math
from harness.self_pulse_rotation import selected_model
from harness.self_pulse_odom import response
from harness.active_wall_mapping import pulse_command, native_profile_valid
from sim.settle_pulse import PulseSettler, proportional_pulse


def turn_quantum(model, *, native_primitives=False):
    values = [abs(response(p, .2)[2]) for key, p in selected_model(model)['profiles'].items()
              if key.startswith('0:') and p['axis'] == 'turn' and p['times'][-1] <= .2+1e-8
              and (not native_primitives or native_profile_valid(p))]
    return min(v for v in values if v > 0)


def settle_turn(settler, error, t, *, costmap, pose, motion_model, native_primitives=False):
    quantum = turn_quantum(motion_model,native_primitives=native_primitives)
    receipt = settler.observe(error, quantum)
    if receipt['settled']:
        return dict(t=float(t), kind='hold'), receipt
    requested = proportional_pulse(error, quantum, maximum=quantum)
    command, predicted = pulse_command([0., 0., requested/.2], t,
        costmap=costmap, pose=pose, motion_model=motion_model,native_primitives=native_primitives)
    if command['kind'] != 'hold':
        settler.issued(error)
    receipt.update(issued=command['kind'] != 'hold', pulse=predicted)
    return command, receipt
