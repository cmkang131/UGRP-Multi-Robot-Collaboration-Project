"""Isolated, default-off torque-limited PD candidate; not measured REAL stiffness.

Provenance/assumptions: experiments/2026-10-07-servo-stiffness/REFERENCES.md.
The 0.3 degree design target is LD positioning accuracy, not an identified K.
"""
import math
import xml.etree.ElementTree as ET

OPTION = 'real_v1'
ACCURACY_DEG = .3
TORQUE_NM = {'arm_yaw': 13*.0980665, 'shoulder': 13*.0980665,
             'elbow': 1.8*.0980665, 'wrist': 1.8*.0980665}


def parameters():
    return {name: dict(kp=torque/math.radians(ACCURACY_DEG),
                      torque_limit_nm=torque, dampratio=1.)
            for name, torque in TORQUE_NM.items()}


def transform_xml(xml, *, servo_stiffness='off', robot_id='r3'):
    if servo_stiffness == 'off':
        return xml
    if servo_stiffness != OPTION or robot_id not in ('r1', 'r2', 'r3'):
        raise ValueError('unsupported servo stiffness / robot')
    root = ET.fromstring(xml)
    option = root.find('option')
    if option is None or option.get('integrator') != 'implicitfast':
        raise ValueError('stiff servo requires existing implicitfast integrator')
    for name, spec in parameters().items():
        nodes = root.findall(f"actuator/position[@name='{robot_id}__servo_{name}']")
        if len(nodes) != 1:
            raise ValueError('expected one named position actuator: '+name)
        actuator = nodes[0]
        actuator.attrib.pop('kv', None)
        actuator.set('kp', repr(spec['kp']))
        actuator.set('dampratio', '1')
        actuator.set('forcelimited', 'true')
        torque = spec['torque_limit_nm']
        actuator.set('forcerange', f'{-torque} {torque}')
    return ET.tostring(root, encoding='unicode')
