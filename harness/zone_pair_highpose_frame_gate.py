"""v98 own-image frame gate: the frozen ``zone_pair_vision`` rules with the floor_light_v1 contrast values.

``harness/zone_pair_vision.py`` is frozen: earlier bundles pin its bytes and it stays byte-identical to main.
Its contrast rule (1-99 percentile spread >= 15, V std >= 3) rejected valid flat floor views under the
floor_light_v1 render profile, so v98 uses the registered values of
``configs/calibration/own_image_gates_floor_light_v1.json`` (sha256 pinned in the v98 registry,
``own_image_gates``). Only those two numbers differ; freshness, JPEG, shape, the calibrated fisheye rim and both
dark-fraction rules are the frozen ones (``FrameGate(15., 3.)`` reproduces the frozen verdicts, see tests).

No module global, imported class, file or process import hook is patched; there is no process-level state.
The v98 classes run the frozen method code objects with a private builtins dictionary whose ``__import__``
answers the two local imports ``from harness.zone_pair_vision import ...`` and
``from harness.zone_pair_admission import readiness_snapshot`` with v98 views of those modules (``gated``).
Every other import is the normal one. The admission check keeps its own rule: it imports ``valid_frame``
(never ``frame_gate``), so the v98 admission image check is ``valid_frame`` with the v98 values.

The bound copies read their module globals as they were when this module was imported, so a later test or
probe patch of e.g. ``harness.zone_pair_vision.valid_frame`` (``scripts/run_pair_stage_probes.py``
``image_valid_off``) does not reach v98; those tools target earlier bundles.
"""
import base64
import builtins
import functools
import types

import cv2
import numpy as np

from harness import zone_pair_admission as admission
from harness import zone_pair_vision as frozen
from harness.m1_owncam_contract import validate_observation
from harness.owncam_pair_beam_v2 import _valid
from harness.zone_final_pair_binding import bind

PROFILE = 'zone_pair_frame_gate_floor_light_v1_v98'
_ERRORS = (ValueError, TypeError, KeyError, AttributeError, RuntimeError, cv2.error)


class FrameGate:
    """``zone_pair_vision.valid_frame``/``valid_frame_ob``/``frame_gate`` with explicit contrast values."""

    def __init__(self, spread_min, std_min):
        self.spread_min, self.std_min = float(spread_min), float(std_min)

    @classmethod
    def from_values(cls, values):
        return cls(values['frame_contrast_spread_min'], values['frame_value_std_min'])

    def _contrast_ok(self, value):
        low, high = np.percentile(value, [1, 99])
        return bool(high - low >= self.spread_min and value.std() >= self.std_min)

    @staticmethod
    def _frame(obs, rid, now):
        # Same order and rules as the frozen valid_frame / valid_frame_ob prefix.
        validate_observation(obs, robot_id=rid, previous_frame_id=None, now=now)
        if (type(obs['frame_id']) is not int or obs['frame_id'] < 0
                or not 0 <= now - obs['sim_time'] <= .25):
            return None
        jpeg = base64.b64decode(obs['image'], validate=True)
        if not jpeg.startswith(b'\xff\xd8') or not jpeg.endswith(b'\xff\xd9'):
            return None
        frame = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        if frame is None or frame.shape != (480, 640, 3):
            return None
        return frame

    def valid_frame(self, obs, rid, now):
        try:
            frame = self._frame(obs, rid, now)
            if frame is None:
                return False
            value = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)[..., 2][_valid()]
            return bool((value < 8).mean() < .25 and self._contrast_ok(value))
        except _ERRORS:
            return False

    def valid_frame_ob(self, obs, rid, now):
        try:
            frame = self._frame(obs, rid, now)
            if frame is None:
                return False
            v_channel = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)[..., 2]
            value = v_channel[_valid()]
            return bool((value <= frozen.dark_level(v_channel)).mean() < .25 and self._contrast_ok(value))
        except _ERRORS:
            return False

    def frame_gate(self, policy):
        """``zone_pair_vision.frame_gate``: the per-step gate of a pair policy."""
        return self.valid_frame_ob if getattr(policy, 'own_image_ob', False) else self.valid_frame

    def controller_gate(self, controller):
        """``zone_pair_grasp._frame_gate``: the gate of a controller's policy."""
        return self.frame_gate(getattr(controller, 'policy', None))


@functools.lru_cache(maxsize=None)
def gate():
    """The registered v98 gate (values from the sha256-pinned own_image_gates file)."""
    from harness.zone_pair_highpose_contract import own_image_gates
    return FrameGate.from_values(own_image_gates()['values'])


def controller_gate(controller):
    return gate().controller_gate(controller)


@functools.lru_cache(maxsize=None)
def _views():
    g = gate()
    vision = types.ModuleType('harness.zone_pair_vision[v98]')
    vision.valid_frame, vision.valid_frame_ob, vision.frame_gate = g.valid_frame, g.valid_frame_ob, g.frame_gate
    vision.PROFILE = PROFILE
    adm = types.ModuleType('harness.zone_pair_admission[v98]')
    adm.readiness_snapshot = gated(admission.readiness_snapshot)
    return {'harness.zone_pair_vision': vision, 'harness.zone_pair_admission': adm}


_TARGETS = ('harness.zone_pair_vision', 'harness.zone_pair_admission')


def _import(name, globals=None, locals=None, fromlist=(), level=0):
    if level == 0 and name in _TARGETS:
        if not fromlist:
            raise ImportError(f'v98 frame gate: only "from {name} import ..." is answered')
        return _views()[name]
    if level == 0 and name == 'harness' and fromlist and {'zone_pair_vision', 'zone_pair_admission'} & set(fromlist):
        raise ImportError('v98 frame gate: "from harness import zone_pair_vision/admission" is not answered')
    return builtins.__import__(name, globals, locals, fromlist, level)


BUILTINS = {**vars(builtins), '__import__': _import}


def gated(function, **dependencies):
    """``bind`` the frozen ``function`` (same code object and closure) with the v98 private builtins."""
    return bind(function, __builtins__=BUILTINS, **dependencies)


def is_gated(function):
    function = getattr(function, '__func__', function)
    return function.__globals__.get('__builtins__') is BUILTINS


def record():
    g = gate()
    return {'profile': PROFILE, 'module': 'harness/zone_pair_highpose_frame_gate.py',
            'frozen_module': 'harness/zone_pair_vision.py', 'values_from': 'own_image_gates',
            'frame_contrast_spread_min': g.spread_min, 'frame_value_std_min': g.std_min,
            'process_global_state': False}
