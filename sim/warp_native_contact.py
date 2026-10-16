"""Explicit MJWarp contact experiments; importing this module changes nothing.

The legacy profile and all world builders remain unchanged. See the pinned
sources and the measured acceptance distribution in experiments/2026-10-16-warpfit.
"""
from copy import deepcopy
import hashlib
import json
import xml.etree.ElementTree as ET

PLAYGROUND = 'd59156e099a8785dd58fbce2e25a6ee1f7b5800c'
PROFILES = {
    'baseline_noslip10': {},
    # Aloha uses impratio=5. Keep the existing material and contact model to
    # isolate removal of the expensive hard-friction postprocessor.
    'warp_native_contact_v1': {'noslip_iterations': '0', 'cone': 'elliptic',
                               'integrator': 'implicitfast', 'impratio': '5'},
    # Robotiq/Aloha fingertip contact: 0.01s critically damped reference and
    # solimp .99/.995/.01. Retain our measured/model material coefficients.
    'warp_native_contact_v2': {'noslip_iterations': '0', 'cone': 'elliptic',
                               'integrator': 'implicitfast', 'impratio': '5'},
    # Playground's Panda/Robotiq scene uses exactly 10 Newton + 10 line-search
    # iterations. This is an explicitly measured performance candidate only.
    'warp_native_fast_v1': {'noslip_iterations': '0', 'cone': 'elliptic',
                          'integrator': 'implicitfast', 'impratio': '5',
                          'iterations': '10', 'ls_iterations': '10'},
}


def apply(xml, profile='baseline_noslip10'):
    if profile not in PROFILES:
        raise ValueError('unknown native contact profile')
    if profile == 'baseline_noslip10':
        return xml  # Byte-preserving default, including whitespace.
    root = ET.fromstring(xml)
    option = root.find('option')
    if option is None:
        raise ValueError('explicit source option required')
    option.attrib.update(PROFILES[profile])
    if any(e.get('active', 'true') != 'false' for e in root.findall('equality/weld')):
        raise ValueError('weld assistance must be OFF')
    if profile in ('warp_native_contact_v2', 'warp_native_fast_v1'):
        count = 0
        for pair in root.findall('contact/pair'):
            names = (pair.get('geom1', ''), pair.get('geom2', ''))
            if any(n.endswith(('__left_finger', '__right_finger')) for n in names):
                pair.set('condim', '3')
                pair.set('solref', '0.01 1')
                pair.set('solimp', '0.99 0.995 0.01 0.5 2')
                # Zero means use the normal reference for friction. Remove the
                # old damping-only 0/-6000 override rather than combining both.
                pair.set('solreffriction', '0 0')
                count += 1
        if not count:
            raise ValueError('declared fingertip contact pairs required')
    return ET.tostring(root, encoding='unicode')


def record(profile):
    value = dict(profile=profile, options=deepcopy(PROFILES[profile]),
                 playground_commit=PLAYGROUND, default_off=profile != 'baseline_noslip10')
    value['sha256'] = hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
    return value
