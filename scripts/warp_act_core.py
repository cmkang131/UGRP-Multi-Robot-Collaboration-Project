"""Array command decoding for the opt-in Warp backend; no simulator import.

All state is issued-command state. No qpos, contacts or measured motion enter.
Constants below are copied from CameraRobotPort / v7 DriveParameters at the
frozen ACT11 source, rather than new acceptance thresholds.
"""
import numpy as np

SERVOS = (1, 3, 4, 5, 6)


def relay(command, previous, *, start_fraction, kinetic_fraction):
    u = np.asarray(command, dtype=float)
    state = np.asarray(previous, dtype=int)
    if u.shape != state.shape or u.ndim != 2 or u.shape[1] != 4:
        raise ValueError('matching [world,4] command and relay arrays required')
    if not np.isfinite(u).all() or np.any(np.abs(u) > 1) or not np.isin(state, [-1, 0, 1]).all():
        raise ValueError('finite normalized issued commands required')
    sign = np.sign(u).astype(int)
    active = (np.abs(u) > start_fraction) | ((state != 0) & (sign == state) & (np.abs(u) > kinetic_fraction))
    return np.where(active, u-sign*kinetic_fraction, 0.), np.where(active, sign, 0)


def visible_relative(visible_n, probe_n, holding, read_selected):
    """Lazy vector boundary: callback receives ONLY allowed world indices."""
    seen, total, held = np.asarray(visible_n), np.asarray(probe_n), np.asarray(holding, dtype=bool)
    if seen.shape != total.shape or seen.shape != held.shape or seen.ndim != 1:
        raise ValueError('matching world masks required')
    if np.any(total < 0) or np.any(seen < 0) or np.any(seen > total):
        raise ValueError('invalid visibility counts')
    allowed = (~held) & (total > 0) & (seen >= np.ceil(total/3))
    ids = np.flatnonzero(allowed)
    # Shape and field whitelist prevent bulk truth from escaping this adapter.
    value = read_selected(ids) if len(ids) else np.empty((0, 4))
    value = np.asarray(value, dtype=float)
    if value.shape != (len(ids), 4) or not np.isfinite(value).all():
        raise ValueError('only finite selected-world xyz,yaw measurements accepted')
    return ids, value


def control_tape(rows, relay_state, *, dt, steps, lookup, wheel_ids, servo_ids,
                 start_fraction, kinetic_fraction, torque_cap_nm):
    """Vectorize worlds; loop only over the fixed 400 physics ticks / 0.1s.

    Match DutyActPort.tick and CameraRobotPort fractional interpolation,
    including nearest-even integer PWM rounding before actuator mapping.
    Each row contains command-state snapshots and the existing ctrl template.
    """
    if not rows or steps <= 0 or dt <= 0 or not np.isfinite(dt):
        raise ValueError('positive physics clock and nonempty world batch required')
    ctrl = np.stack([r['ctrl'] for r in rows]).astype(float)
    wheels = np.stack([r['wheels'] for r in rows]).astype(float)
    deadlines = np.stack([r['deadlines'] for r in rows]).astype(float)
    applied = np.stack([r['applied'] for r in rows]).astype(float)
    target = np.stack([r['target'] for r in rows]).astype(float)
    servo_active = np.stack([r['servo_active'] for r in rows]).astype(bool)
    now = np.asarray([r['now'] for r in rows], dtype=float)
    previous_time = np.asarray([r['servo_time'] for r in rows], dtype=float)
    state = np.asarray(relay_state).copy()
    if (wheels.shape != (len(rows), 4) or applied.shape != (len(rows), 5)
            or not np.isfinite(ctrl).all() or not np.isfinite(applied).all()):
        raise ValueError('invalid command-state batch')
    tape = np.empty((steps, len(rows), ctrl.shape[1]), dtype=np.float32)
    pwm = np.rint(applied).astype(int)
    for tick in range(steps):
        at = now+tick*dt
        allowance = 2000.*(at-previous_time)[:, None]  # frozen port rate, PWM/s
        if np.any(allowance < -1e-12):
            raise ValueError('issued command clock moved backwards')
        applied = np.where(servo_active, applied+np.clip(target-applied, -allowance, allowance), applied)
        pwm = np.rint(applied).astype(int)
        if np.any(pwm < 500) or np.any(pwm > 2500):
            raise ValueError('servo command outside original hardware range')
        for k, ids in enumerate(servo_ids):
            ctrl[:, ids] = lookup[k, pwm[:, k]-500][:, None]
        servo_active &= np.abs(applied-target) >= 1e-9  # original accumulator completion
        wheels = np.where((deadlines > 0) & (at[:, None] >= deadlines), 0., wheels)
        effective, state = relay(wheels, state, start_fraction=start_fraction, kinetic_fraction=kinetic_fraction)
        ctrl[:, wheel_ids] = torque_cap_nm*effective
        tape[tick] = ctrl
        previous_time = at
    return tape, dict(relay=state, wheels=wheels, applied=applied, pwm=pwm,
                      target=target, servo_active=servo_active, servo_time=previous_time)


def model_key(xml):
    """Same scene/model excluding only free-body initial pose declarations.

    MuJoCo free-joint qpos stores that pose per world. Static bodies, geometry,
    dynamics, materials, sensors and camera parameters must remain exact.
    No approximate numeric model matching or mixed-map batching is admitted.
    """
    import hashlib
    import xml.etree.ElementTree as ET
    root=ET.fromstring(xml)
    for body in root.iter('body'):
        free=body.find('freejoint') is not None or any(j.get('type')=='free' for j in body.findall('joint'))
        if free:
            for attr in ('pos','quat','euler','axisangle','xyaxes','zaxis'):
                body.attrib.pop(attr,None)
    return hashlib.sha256(ET.tostring(root)).hexdigest()


def varying_model_arrays(rows, batchable):
    """Exact converted-model array audit; no unsupported field is shared.

    Leading singleton dimensions come from pinned MJWarp put_model. Concatenate
    supported fields in world order; return only differing arrays to upload.
    """
    if not rows or any(set(row)!=set(rows[0]) for row in rows):
        raise ValueError('matching converted model fields required')
    out={}
    for key,first in rows[0].items():
        values=[np.asarray(row[key]) for row in rows]
        if any(v.shape!=values[0].shape or v.dtype!=values[0].dtype for v in values):
            raise ValueError('model layout differs: '+key)
        if all(np.array_equal(values[0],v) for v in values[1:]):continue
        if key not in batchable or not values[0].ndim or values[0].shape[0]!=1:
            raise ValueError('unbatchable model difference: '+key)
        out[key]=np.concatenate(values,axis=0)
    return out


def masked_restore(current, initial, mask):
    """Restore selected integration rows; preserve every untouched row exactly."""
    selected=np.asarray(mask)
    if selected.dtype!=np.bool_ or selected.ndim!=1 or set(current)!=set(initial):
        raise ValueError('boolean world mask and matching integration fields required')
    out={}
    for name,value in current.items():
        value=np.asarray(value);start=np.asarray(initial[name])
        if value.shape!=start.shape or value.dtype!=start.dtype or not value.ndim or value.shape[0]!=len(selected):
            raise ValueError('integration reset layout mismatch: '+name)
        restored=value.copy();restored[selected]=start[selected];out[name]=restored
    return out
