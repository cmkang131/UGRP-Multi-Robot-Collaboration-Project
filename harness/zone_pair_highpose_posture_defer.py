"""v98 only: never start an align re-look during an arm posture transition, never observe from an unmeasured posture.

Finding (af2f7c2a probes, r2): the look posture switched p45 -> inspect at 24.9 s (``_set_look``, 0.6 s
interpolation). At 25.0 s the align tick raised a ``fix_gap`` re-look; the shared ``_begin_align_relook`` clears
the arm queue and keeps the issued PWM, so the arm stopped after its first interpolation step at 765/1991/1865
(look 1500). No camera model is measured for that posture; 0.3 s later the provider failed closed
(``UNMEASURED_V3_CAMERA_POSTURE``) and every later fix check was refused (``ALIGN_RELOOK_NO_FIX``).

Rule (coordinator ruling 2026-10-04), the standard behaviour-tree semantics: a non-safety condition does not
preempt a running motion primitive (BehaviorTree.CPP ``Sequence`` resumes a RUNNING child; only a reactive node
halts it), and a halted primitive must leave a safe state.

* A re-look request (any reason, from the align tick or a direct ``_begin_align_relook`` call) is queued while
  arm interpolation events are pending. It starts once the arm has reached its commanded target and the issued
  posture has a measured camera model for the provider's reported load state. The chassis is held once when the
  request is queued (the align handler issues no base motion while the arm moves either); the fixed-enum status
  and the partner-abort check keep running every tick, exactly as in the re-look states.
* If the arm is idle at an unmeasured posture in ``align`` (any other interruption), it returns to the last
  measured posture at once (the provider fails closed on its next settled frame, 0.3 s), and a queued re-look
  starts only after that. Without a known measured posture the request fails (``ALIGN_RELOOK_UNMEASURED_POSTURE``).
* The wait is bounded by the existing per-look allowance ``zone_pair_align.MAX_LOOK_S`` (no new threshold):
  ``ALIGN_RELOOK_DEFER_TIMEOUT``.

Inputs: issued PWM (``port.own.servo``), the controller's own arm queue, the provider's own report
(``load_state``) and the static calibration's measured camera-model keys. No plant state, no partner pose.
Shared modules are unchanged; the mixin sits in front of the v98 controller class.
"""
from __future__ import annotations

from harness.vision_pose_source_final import camera_key
from harness.zone_pair_align import MAX_LOOK_S, PairAlignRelook

ID = 'v98_relook_posture_defer_v1'
ARM_SERVOS = (3, 4, 5, 6)
TIMEOUT_CODE = 'ALIGN_RELOOK_DEFER_TIMEOUT'
NO_RESTORE_CODE = 'ALIGN_RELOOK_UNMEASURED_POSTURE'
REFERENCES = ('BehaviorTree.CPP Sequence / ReactiveSequence (behaviortree.dev, nodes-library/SequenceNode)',
              'BehaviorTree.CPP asynchronous actions, halt()/onHalted (behaviortree.dev, guides/asynchronous_nodes)')


def measured_keys(calibration) -> dict:
    """``{'loaded'|'unloaded': frozenset(camera keys)}`` from the static measured calibration (never the plant)."""
    models = calibration['camera_models']
    return {state: frozenset(models.get(state, {})) for state in ('loaded', 'unloaded')}


def load_state(ctl) -> str:
    report = getattr(ctl.port.own, 'last_report', None)
    state = getattr(report, 'load_state', None)
    return state if state in ('loaded', 'unloaded') else 'unloaded'


def posture(ctl, now) -> dict:
    """Own arm state: pending interpolation, issued posture, whether it is a measured camera posture."""
    arm, issued = ctl.arm, dict(ctl.port.own.servo)
    key = camera_key(issued)
    load = load_state(ctl)
    measured = key in ctl.v98_measured_camera_keys[load]
    moving = bool(arm.events)
    at_target = all(issued.get(s) == arm.commanded.get(s) for s in ARM_SERVOS)
    return {'key': key, 'load_state': load, 'measured': measured, 'moving': moving, 'at_target': at_target,
            'ready': (not moving) and at_target and measured}


def record() -> dict:
    return {'id': ID, 'rule': 'align re-look queued while arm interpolation is pending; starts at the reached '
                              'commanded target with a measured camera model; idle at an unmeasured posture -> '
                              'return to the last measured posture first',
            'bound_s': MAX_LOOK_S, 'timeout_code': TIMEOUT_CODE, 'no_restore_code': NO_RESTORE_CODE,
            'chassis_hold_on_queue': True, 'status_and_partner_abort_each_tick': True,
            'shared_sources_modified': False, 'references': list(REFERENCES)}


class DeferRelook:
    """Mixin placed in front of the v98 pair controller (``runtime.controller_class``)."""

    def _v98_defer_log(self, kind, now, **values):
        rows = self.__dict__.setdefault('v98_relook_defer', [])
        rows.append({'event': kind, 'sim_s': round(float(now), 4), 'state': self.state, **values})
        self.log(self.rid, kind, now, **values)

    def _v98_note_measured(self, now):
        if getattr(self, 'v98_measured_camera_keys', None) is None:
            return None          # not an Execution-built v98 controller (unit fixtures); the align path raises
        st = posture(self, now)
        if st['ready']:
            self.v98_last_measured_posture = {s: int(self.port.own.servo[s]) for s in ARM_SERVOS}
        return st

    def _begin_align_relook(self, now, reason):
        st = self._v98_note_measured(now)
        if st is None:
            raise RuntimeError('v98 re-look posture deferral needs the measured camera keys (Execution sets them)')
        pending = getattr(self, 'v98_relook_pending', None)
        if st['ready']:
            if pending is not None:
                self.v98_relook_pending = None
                self._v98_defer_log('align_relook_defer_end', now, reason=pending['reason'],
                                    waited_s=round(now - pending['since'], 4), posture_key=st['key'])
            return super()._begin_align_relook(now, reason)
        if pending is None:
            self.v98_relook_pending = {'reason': reason, 'since': float(now), 'restored': False}
            self._v98_defer_log('align_relook_deferred', now, reason=reason, posture_key=st['key'],
                                load_state=st['load_state'], moving=st['moving'], at_target=st['at_target'],
                                measured=st['measured'])
            if self.state != 'align':
                # Entered from ``set('align')``: the shared path would go straight to the re-look stop. Enter
                # align without its handler work; the queued request fires from ``tick`` once ready.
                seg = {'seg': self.seg} if hasattr(self, 'seg') else {}     # what V3Controller.set adds
                super(PairAlignRelook, self).set('align', now, **seg)
            self.port.hold(now)
        return self._v98_wait(now, st)

    def _v98_wait(self, now, st):
        pending = self.v98_relook_pending
        self.status[1].tick('aligning', now)
        if any(v['state'] == 'abort' for v in self.status[0].partner_view(self.rid, now).values()):
            self.v98_relook_pending = None
            self.port.hold(now)
            return self.fail('PARTNER_ABORT', now)
        if now - pending['since'] >= MAX_LOOK_S - 1e-8:
            self.v98_relook_pending = None
            return self.fail(TIMEOUT_CODE, now)
        if not st['moving'] and not st['ready'] and not pending['restored']:
            pending['restored'] = True
            return self._v98_restore(now, st)
        return None

    def _v98_restore(self, now, st):
        """Arm idle at an unmeasured posture: go back to the last measured one (never observe from here)."""
        target = getattr(self, 'v98_last_measured_posture', None)
        if target is None:
            self.v98_relook_pending = None
            return self.fail(NO_RESTORE_CODE, now)
        self._v98_defer_log('align_posture_restore', now, from_key=st['key'],
                            to_key=camera_key({**self.port.own.servo, **target}))
        issued = dict(self.port.own.servo)
        self.arm.commanded.update({s: issued[s] for s in ARM_SERVOS})   # interpolate from issued PWM
        self.arm.queue(dict(target), now, duration=.6)
        return None

    def tick(self, now):
        pending = getattr(self, 'v98_relook_pending', None)
        if pending is not None:
            if self.state != 'align':
                self.v98_relook_pending = None
            else:
                st = self._v98_note_measured(now)
                if st['ready']:
                    return self._begin_align_relook(now, pending['reason'])
                return self._v98_wait(now, st)
        st = self._v98_note_measured(now)
        if st is not None and self.state == 'align' and not st['moving'] and not st['measured']:
            # Interrupted in align (any cause) and idle at an unmeasured posture: the provider would fail closed
            # on its next settled frame, so return before anything else runs this tick.
            return self._v98_restore(now, st)
        return super().tick(now)
