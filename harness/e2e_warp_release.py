"""Default-off release relocalization adapter for the e2ewarp owner ABI.

Contract consumed by ``harness.e2e_warp_mission.IntegratedController``:

    factory(robot_id=..., static=...) -> adapter
    adapter.start(instruction, own_report)
    adapter.observe(OwnFrame) -> report with relocalized/static_map_registered
    adapter.command(sim_s) -> issued-command whitelist dict

Allowed inputs are exactly the e2ewarp control boundary: own JPEG, own issued
commands (``OwnFrame``), the authored static map/orders (``static``) and the
per-condition channel messages that the runtime feeds the composition, never
this adapter.  No world/model/measurement/verdict/top-camera input is read
here; this module imports no simulator or physics code and never opens a world
file.  A report must not fabricate relocalized/static_map_registered: this
adapter only forwards own inputs to an injected owner observer/correction
callable and validates the returned evidence, otherwise it fails closed.

Default is off.  The "selfmap_v1" candidate reuses only existing values:
the SEARCH pan servo, the approved +/-500 PWM pan span, the existing
``max(PARAMS['settle_s']) + .1`` view dwell and the fixed three-view sweep;
there is no new tolerance, threshold or map constant.

Contract v1 adds the explicit, default-off ``release_relocalization_memory_v1``:

* ``static`` is not used at all; the adapter binds to the navigator's
  self-centric memory snapshot reported at ``start`` (owner
  ``selfnav_memory_v1``, 64-hex ``memory_sha256``, non-negative
  ``navigator_evidence_revision``, destination kind from the order sheet).
* The owner evidence must echo that snapshot hash and revision and report
  ``memory_registered=true`` with a destination landmark of the bound kind; any
  static-map claim, global map pose or GT/held-world read is rejected as mixed
  evidence.
* If the navigator report is missing or not ready/registered, ``start`` binds
  nothing and every later report/command stays fail-closed (no pan, no view
  collection, no claim).
"""
from __future__ import annotations

import hashlib
import json
import math

from harness.e2ewarp_selfnav import (OWNER as SELFCENTRIC_OWNER,
                                     destination_kind_for,
                                     validate_memory_registration)

OPTION_OFF = 'release_relocalization_off_v1'
OPTION_SELFMAP = 'release_relocalization_selfmap_v1'
OPTION_MEMORY = 'release_relocalization_memory_v1'
OPTIONS = (OPTION_OFF, OPTION_SELFMAP, OPTION_MEMORY)
ENTRY = 'harness.e2e_warp_release:release_factory'
FORBIDDEN_IMPUTATIONS = ('relocalized', 'static_map_registered')
PAN_SPAN_PWM = 500          # SEARCH yaw +/- 500 PWM, same as DiagnosticTask scan
PAN_VIEWS = 3               # fixed three settled own-camera views


def _pan_targets():
    from harness.active_camera import SEARCH
    yaw = int(SEARCH[6])
    targets = []
    for delta in (-PAN_SPAN_PWM, 0, PAN_SPAN_PWM):
        value = yaw + delta
        if not 500 <= value <= 2500:  # existing issued PWM range (grasp_act_contract)
            raise ValueError('approved pan range required')
        targets.append(value)
    return tuple(targets)


def _view_dwell_s():
    from harness.e2e_rgb_vo import PARAMS
    return max(PARAMS['settle_s']) + .1  # existing settle interval + one 10Hz frame


def _static_sha(static):
    try:
        return hashlib.sha256(json.dumps(static, sort_keys=True, default=str).encode()).hexdigest()
    except (TypeError, ValueError) as exc:
        raise ValueError('authored static map must be serializable') from exc


def _memory_binding(own_report, instruction):
    """Bind the release attempt to the navigator's self-centric snapshot.

    Returns ``(binding, None)`` or ``(None, fail_closed_reason)``.  This never
    raises for an unready navigator: the adapter must stay fail-closed, not
    crash the mission.
    """
    try:
        registration = validate_memory_registration(own_report.get('memory_registration'))
    except ValueError as exc:
        return None, 'selfnav_memory_contract_invalid:' + str(exc)
    if registration['ready'] is not True:
        return None, 'selfnav_not_ready'
    if registration['registered'] is not True:
        return None, 'selfnav_memory_unregistered'
    if registration['destination_registered'] is not True:
        return None, 'selfnav_destination_unregistered'
    destination = destination_kind_for((instruction or {}).get('destination_zone'))
    if registration.get('destination_kind') != destination:
        return None, 'selfnav_destination_mismatch'
    landmark = registration.get('destination_landmark')
    if not isinstance(landmark, dict) or landmark.get('kind') != destination:
        return None, 'selfnav_destination_landmark_invalid'
    return dict(navigator_owner=SELFCENTRIC_OWNER,
                memory_sha256=registration['memory_sha256'],
                navigator_evidence_revision=registration['evidence_revision'],
                destination_kind=destination,
                destination_landmark=dict(landmark)), None


class ReleaseRelocalization:
    """Fail-closed owner adapter; no motion/claim is invented without evidence."""

    def __init__(self, robot_id, static=None, *, option=OPTION_OFF, owner=None):
        if robot_id not in ('r1', 'r2', 'r3'):
            raise ValueError('unknown robot_id')
        if option not in OPTIONS:
            raise ValueError('UNKNOWN_RELEASE_RELOCALIZATION_OPTION')
        if owner is not None and not callable(owner):
            raise ValueError('owner relocalizer must be callable')
        self.robot_id, self.static = robot_id, static
        self.option, self.owner = option, owner
        self.memory_mode = option == OPTION_MEMORY
        # Contract v1: the memory mode has no static map (and no static hash).
        self.static_sha256 = None if self.memory_mode else _static_sha(static)
        self.instruction = None
        self.own_report = None
        self.binding = None
        self.binding_reason = None
        self.rows = []
        self.pwm = None
        self.last_t = None
        self.last_view_t = None
        self.view = 0
        self.started = False

    # -- ABI -----------------------------------------------------------------
    def start(self, instruction, own_report):
        if not isinstance(instruction, dict) or 'destination_zone' not in instruction:
            raise ValueError('release requires the LLM task instruction')
        if not isinstance(own_report, dict):
            raise ValueError('release start receives the own navigation report')
        self.instruction = dict(instruction)
        self.own_report = dict(own_report)
        from harness.active_camera import SEARCH
        self.pwm = {str(k): int(v) for k, v in SEARCH.items()}
        self.pwm['1'] = 2000
        self.started, self.view, self.rows = True, 0, []
        self.last_target = self.last_target_t = None
        self.binding, self.binding_reason = None, None
        if self.memory_mode:
            self.binding, self.binding_reason = _memory_binding(self.own_report, self.instruction)

    def observe(self, frame):
        if not self.started:
            raise ValueError('release adapter start required before observe')
        if frame.robot_id != self.robot_id:
            raise ValueError('cross-robot release input rejected')
        if self.last_t is not None and frame.sim_s <= self.last_t:
            raise ValueError('causal own frames required')
        self.last_t = frame.sim_s
        if self.memory_mode and self.binding is None:
            return self._report(False, self.binding_reason or 'selfnav_not_ready', memory=True)
        if not frame.issued:
            return self._report(False, 'own_issued_command_history_required')
        issued_pwm = {str(k): int(v) for k, v in frame.issued[-1]['pwm'].items()}
        current = int(self.last_target) if self.last_target is not None else issued_pwm.get('6')
        settled = (self.last_target is not None and issued_pwm.get('6') == current
                   # float-comparison epsilon only; no new time tolerance
                   and frame.sim_s - self.last_target_t + 1e-9 >= _view_dwell_s())
        row = dict(t=float(frame.sim_s), view=len(self.rows), settled=settled,
                   rgb_sha256=hashlib.sha256(frame.jpeg).hexdigest(),
                   issued=len(frame.issued), pwm=issued_pwm)
        if settled and len(self.rows) < PAN_VIEWS:
            self.rows.append(row)
        return self._owner_report()

    def command(self, now):
        from harness.grasp_act_contract import command
        if not math.isfinite(float(now)):
            raise ValueError('finite command time required')
        pwm = dict(self.pwm or {})
        if self.memory_mode and self.binding is None:
            # Fail closed: no lookaround pan without a bound self-centric memory.
            pwm['1'] = 2000
            value = dict(t=float(now), wheels=[0.] * 4, duration_s=[0.] * 4, pwm=pwm)
            return command(value)
        targets = _pan_targets()
        target = targets[min(len(self.rows), PAN_VIEWS - 1)] if self.started else targets[1]
        if target != self.last_target:
            self.last_target, self.last_target_t = target, float(now)
        pwm[str(6)] = target
        value = dict(t=float(now), wheels=[0.] * 4, duration_s=[0.] * 4, pwm=pwm)
        return command(value)

    # -- owner boundary ------------------------------------------------------
    def _owner_report(self):
        views = len(self.rows)
        if views < PAN_VIEWS:
            return self._report(False, f'own_lookaround_views_{views}_of_{PAN_VIEWS}',
                                memory=self.memory_mode)
        if self.memory_mode:
            return self._owner_report_memory()
        if self.owner is None:
            return self._report(False, 'owner_static_map_acquisition_api_pending')
        evidence = dict(robot_id=self.robot_id, static_sha256=self.static_sha256,
                        instruction=dict(self.instruction or {}),
                        views=[dict(t=r['t'], rgb_sha256=r['rgb_sha256'], pwm=dict(r['pwm']))
                               for r in self.rows[-PAN_VIEWS:]])
        try:
            owner = self.owner(evidence)
        except Exception as exc:  # owner failure is unknown, never a claim
            return self._report(False, 'owner_relocalizer_error:' + type(exc).__name__)
        return self._validate(owner)

    def _owner_report_memory(self):
        if self.owner is None:
            return self._report(False, 'owner_memory_acquisition_api_pending', memory=True)
        binding = self.binding
        evidence = dict(robot_id=self.robot_id,
                        navigator_owner=binding['navigator_owner'],
                        memory_sha256=binding['memory_sha256'],
                        navigator_evidence_revision=binding['navigator_evidence_revision'],
                        destination_kind=binding['destination_kind'],
                        instruction=dict(self.instruction or {}),
                        views=[dict(t=r['t'], rgb_sha256=r['rgb_sha256'], pwm=dict(r['pwm']))
                               for r in self.rows[-PAN_VIEWS:]])
        try:
            owner = self.owner(evidence)
        except Exception as exc:  # owner failure is unknown, never a claim
            return self._report(False, 'owner_relocalizer_error:' + type(exc).__name__, memory=True)
        return self._validate_memory(owner)

    def _validate(self, owner):
        if not isinstance(owner, dict):
            return self._report(False, 'owner_report_not_mapping')
        if owner.get('owner') != 'warp8f':
            return self._report(False, 'owner_must_be_warp8f')
        if owner.get('relocalized') is not True:
            return self._report(False, 'owner_relocalized_false')
        if owner.get('static_map_registered') is not True:
            return self._report(False, 'owner_static_map_registered_false')
        if owner.get('static_map_sha256') != self.static_sha256:
            return self._report(False, 'owner_static_map_hash_mismatch')
        if owner.get('truth_inputs', 0) != 0 or owner.get('held_world_reads', 0) != 0:
            return self._report(False, 'owner_reports_forbidden_inputs')
        pose = owner.get('map_pose')
        if (not isinstance(pose, (list, tuple)) or len(pose) != 3
                or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
                       for v in pose)):
            return self._report(False, 'owner_pose_invalid')
        return self._report(True, 'owner_accepted_own_rgb_relocalization',
                           map_pose=[float(v) for v in pose],
                           evidence=dict(source=str(owner.get('source', '')),
                                         views=int(owner.get('views', 0)),
                                         static_map_sha256=self.static_sha256))

    def _validate_memory(self, owner):
        """Validate self-centric owner evidence; any map/GT claim is mixed evidence."""
        binding = self.binding
        if not isinstance(owner, dict):
            return self._report(False, 'owner_report_not_mapping', memory=True)
        if owner.get('owner') != 'warp8f':
            return self._report(False, 'owner_must_be_warp8f', memory=True)
        if owner.get('relocalized') is not True:
            return self._report(False, 'owner_relocalized_false', memory=True)
        if owner.get('memory_registered') is not True:
            return self._report(False, 'owner_memory_registered_false', memory=True)
        if owner.get('static_map_registered') is True or owner.get('static_map_sha256') is not None:
            return self._report(False, 'owner_mixed_static_map_evidence', memory=True)
        if owner.get('memory_sha256') != binding['memory_sha256']:
            return self._report(False, 'owner_memory_hash_mismatch', memory=True)
        if owner.get('navigator_evidence_revision') != binding['navigator_evidence_revision']:
            return self._report(False, 'owner_navigator_revision_mismatch', memory=True)
        if owner.get('truth_inputs', 0) != 0 or owner.get('held_world_reads', 0) != 0:
            return self._report(False, 'owner_reports_forbidden_inputs', memory=True)
        if owner.get('map_pose') is not None:
            return self._report(False, 'owner_map_pose_forbidden', memory=True)
        landmark = owner.get('memory_landmark')
        if not isinstance(landmark, dict) or landmark.get('kind') != binding['destination_kind']:
            return self._report(False, 'owner_destination_landmark_mismatch', memory=True)
        last_seen = landmark.get('last_seen_s')
        if (isinstance(last_seen, bool) or not isinstance(last_seen, (int, float))
                or not math.isfinite(last_seen)):
            return self._report(False, 'owner_landmark_time_invalid', memory=True)
        if last_seen > self.rows[-1]['t'] + 1e-6:
            return self._report(False, 'owner_landmark_from_future', memory=True)
        evidence = dict(navigator_owner=binding['navigator_owner'],
                        memory_sha256=binding['memory_sha256'],
                        navigator_evidence_revision=binding['navigator_evidence_revision'],
                        destination_kind=binding['destination_kind'],
                        source=str(owner.get('source', '')),
                        views=int(owner.get('views', len(self.rows))),
                        view_sha256=[r['rgb_sha256'] for r in self.rows[-PAN_VIEWS:]])
        return self._report(True, 'owner_accepted_self_centric_memory', memory=True,
                            memory_landmark=dict(landmark), evidence=evidence)

    def _report(self, accepted, reason, *, memory=False, map_pose=None, evidence=None,
                row=None, memory_landmark=None):
        audit = dict(option=self.option, views=len(self.rows), truth_inputs=0,
                     held_world_reads=0, top_camera_control=False,
                     static_map_input=not memory)
        if memory:
            report = dict(relocalized=bool(accepted), memory_registered=bool(accepted),
                          static_map_registered=False, reason=reason, map_pose=None,
                          pose_estimate=dict(frame='self_centric', position_xy=[0.0, 0.0]),
                          navigator_owner=(None if self.binding is None
                                           else self.binding['navigator_owner']),
                          memory_sha256=(None if self.binding is None
                                         else self.binding['memory_sha256']),
                          navigator_evidence_revision=(None if self.binding is None
                                                       else self.binding['navigator_evidence_revision']),
                          memory_landmark=memory_landmark, evidence=evidence, audit=audit)
        else:
            report = dict(relocalized=bool(accepted), static_map_registered=bool(accepted),
                          reason=reason, map_pose=map_pose, evidence=evidence, audit=audit)
        if row is not None:
            report['row'] = row
        return report


def release_factory(robot_id, static=None, *, option=OPTION_OFF, owner=None):
    """Manifest entry point: module:release_factory, called with robot_id/static."""
    return ReleaseRelocalization(robot_id, static, option=option, owner=owner)
