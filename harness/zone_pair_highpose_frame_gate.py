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

Own-load occlusion (``zone_pair_highpose_own_load_occlusion``, 2026-10-05). ``FrameGate.assess`` splits the frame
verdict in three: ``VALID``; ``CONTENT_ONLY`` (a fresh, decodable, correctly shaped frame that fails only the
dark-fraction / contrast rule); ``INVALID`` (stale, undecodable, wrong shape, malformed). ``valid_frame`` and
``valid_frame_ob`` are ``assess(...)[0] == VALID``, so every boolean answer is the one given before this split.
``gated_accepted`` is a second private builtins dictionary for the frozen ``PairExecution.step``/``arm_step``
code objects only: its ``frame_gate`` accepts. It is chosen per call by the v98 ``Execution`` after the occlusion
rule has classified the frame; it is never reachable from any other function.
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
VALID, CONTENT_ONLY, INVALID = 'valid', 'content_only', 'invalid'


class FrameGate:
    """``zone_pair_vision.valid_frame``/``valid_frame_ob``/``frame_gate`` with explicit contrast values."""

    def __init__(self, spread_min, std_min):
        self.spread_min, self.std_min = float(spread_min), float(std_min)

    @classmethod
    def from_values(cls, values):
        return cls(values['frame_contrast_spread_min'], values['frame_value_std_min'])

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

    def assess(self, obs, rid, now, *, ob):
        """``(verdict, measures)``: ``VALID``, ``CONTENT_ONLY`` or ``INVALID``.

        ``ob`` selects the dark-fraction rule of ``valid_frame_ob`` (``frozen.dark_level``) instead of the fixed
        ``V < 8`` of ``valid_frame``. ``CONTENT_ONLY`` means the frame passed every prefix check (observation
        contract, age, JPEG markers, shape) and failed only the dark-fraction / contrast rule; ``measures`` then
        holds the three values the rule read. ``INVALID`` carries no measures.
        """
        try:
            frame = self._frame(obs, rid, now)
            if frame is None:
                return INVALID, None
            v_channel = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)[..., 2]
            value = v_channel[_valid()]
            dark = float((value <= frozen.dark_level(v_channel)).mean() if ob else (value < 8).mean())
            low, high = np.percentile(value, [1, 99])
            spread, std = float(high - low), float(value.std())
            measures = {'dark_fraction': dark, 'value_spread': spread, 'value_std': std}
            ok = bool(dark < .25 and high - low >= self.spread_min and value.std() >= self.std_min)
            return (VALID if ok else CONTENT_ONLY), measures
        except _ERRORS:
            return INVALID, None

    def valid_frame(self, obs, rid, now):
        return self.assess(obs, rid, now, ob=False)[0] == VALID

    def valid_frame_ob(self, obs, rid, now):
        return self.assess(obs, rid, now, ob=True)[0] == VALID

    def assessor(self, policy):
        """The verdict function of a pair policy (the ``frame_gate`` selection rule)."""
        ob = bool(getattr(policy, 'own_image_ob', False))
        return lambda obs, rid, now: self.assess(obs, rid, now, ob=ob)

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


def _accepting_gate(policy):
    """``frame_gate`` of the accepted view: the caller already classified this frame (see ``gated_accepted``)."""
    return _accepts


def _accepts(obs, rid, now):
    return True


@functools.lru_cache(maxsize=None)
def _views_accepted():
    vision = types.ModuleType('harness.zone_pair_vision[v98 accepted]')
    vision.frame_gate = _accepting_gate
    vision.PROFILE = PROFILE
    return {'harness.zone_pair_vision': vision, 'harness.zone_pair_admission': _views()['harness.zone_pair_admission']}


def _import_accepted(name, globals=None, locals=None, fromlist=(), level=0):
    if level == 0 and name in _TARGETS:
        if not fromlist:
            raise ImportError(f'v98 frame gate: only "from {name} import ..." is answered')
        return _views_accepted()[name]
    return _import(name, globals, locals, fromlist, level)


BUILTINS_ACCEPTED = {**vars(builtins), '__import__': _import_accepted}


def gated(function, **dependencies):
    """``bind`` the frozen ``function`` (same code object and closure) with the v98 private builtins."""
    return bind(function, __builtins__=BUILTINS, **dependencies)


def gated_accepted(function):
    """``bind`` the frozen ``function`` so its ``frame_gate`` accepts: for ``PairExecution.step``/``arm_step`` only.

    The caller (``zone_pair_highpose_own_load_occlusion``) has classified this tick's frame as ``VALID`` or
    ``OCCLUDED_BY_OWN_LOAD`` with the same ``FrameGate.assess`` the gated copy would run; a stale, undecodable,
    wrong-shape or (outside a loaded phase) occluded frame is never routed here.
    """
    return bind(function, __builtins__=BUILTINS_ACCEPTED)


def is_gated(function):
    function = getattr(function, '__func__', function)
    private = function.__globals__.get('__builtins__')
    return private is BUILTINS or private is BUILTINS_ACCEPTED


def is_gated_accepted(function):
    function = getattr(function, '__func__', function)
    return function.__globals__.get('__builtins__') is BUILTINS_ACCEPTED


def record():
    g = gate()
    return {'profile': PROFILE, 'module': 'harness/zone_pair_highpose_frame_gate.py',
            'frozen_module': 'harness/zone_pair_vision.py', 'values_from': 'own_image_gates',
            'frame_contrast_spread_min': g.spread_min, 'frame_value_std_min': g.std_min,
            'process_global_state': False}
