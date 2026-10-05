"""v98 own-load occlusion rule: a camera blocked by the beam the robot itself holds is "no observation", not a fault.

Failure (first LLM DEV run, ``pair-llm-DEV-v103b-light-s911-8a1acdad-fast1``, no_comm). With the near plane of
``floor_light_nearclip_v1`` (4.4 mm, ``sim/final_pair_highpose_nearclip``) the held beam fills the own camera view
once the arm is lowered for a mid-route set-down: frame 06704 (SIM 336.5) is a dark grey view with a thin floor
band, frame 06734 (SIM 338.0) is uniform (value spread 0, std 0.22). The per-step own-image gate of the frozen
``PairExecution.step``/``arm_step`` (``INVALID_OWN_IMAGE``) refused the frame, aborted r1's job at SIM 338.05 and r2
followed with ``PARTNER_ABORT``. Before the near-plane fix the beam was clipped away and the floor showed through, so
the gate never fired.

Rule. While THIS robot is in a loaded phase, a frame that is fresh, decodable and correctly shaped but fails only the
dark-fraction / contrast rule (``FrameGate.assess`` verdict ``CONTENT_ONLY``) is classified
``OCCLUDED_BY_OWN_LOAD``. It is logged (``own_image_occluded_by_own_load`` at the start of an episode,
``own_image_occlusion_ended`` at its end, counts in the record) and the step goes on: the commanded motion (arm
lowering, wait for the partner barrier, release) continues from the controller's own command history, and the frame is
marked ``own_image = OCCLUDED_BY_OWN_LOAD`` in every grip-monitor row that carries its ``frame_id``, i.e. it is no
observation. Nothing is inferred from the occluded frame.

Loaded phase = both of the controller's own signals agree: its phase is one of ``LOADED_PHASES`` (grip closed and
held from the lift to the final-release barrier, including the sigma decision stop and the set-down) and its own
grasp receipt says held (``beam_grasp_confirmed``: receipt of the current segment and the issued gripper pulse still
closed, i.e. the own issued-command history). After the open is issued the receipt is gone, but the beam still sits in
front of the camera until the arm has risen: ``RELEASE_PHASES`` (``cp_open`` and ``released``) count as loaded for as
long as the controller's own queued arm motion (open, hover, search) has not finished. Outside these windows the
frame gate is unchanged.

Hard stops kept: a stale, undecodable, wrong-shaped or malformed frame (``INVALID``) in any phase, and a
dark/uniform frame outside the loaded windows (an occluded view while unloaded, e.g. at the grasp posture or at
admission) abort with ``INVALID_OWN_IMAGE`` exactly as before. Inputs are the own image, the own issued commands and
the own controller phase; no ground truth, joint measurement or contact. The rule is a sensing rule, not a DEV soft
stop: it applies in formal and DEV runs alike (it does not read ``DEV_LIGHT``).

How. ``zone_pair_highpose_runtime.Execution.step``/``arm_step`` ask ``OwnLoadOcclusion.accepts``. When it answers
yes the frozen code object runs with ``frame_gate.gated_accepted`` (its ``frame_gate`` accepts: the frame was
classified ``VALID`` or ``OCCLUDED_BY_OWN_LOAD`` by the same ``FrameGate.assess`` the gated copy would have run);
otherwise it runs with the unchanged v98 gate. Outside a loaded window ``accepts`` returns at once and the gate runs
as before. The verdict is memoised per (frame, tick), so a loaded step decodes each frame once.

References (marks as in the experiment README: [F] page opened and read, [S] search summary only, [K] background):
* Treat a missing measurement as no update and go on from the motion model: the Kalman filter article ("Details":
  when an observation is unavailable the update step may be skipped and the prediction repeated) [F, Wikipedia];
  ``robot_localization`` ``sensor_timeout``: once a sensor has been silent longer than the timeout the node runs a
  predict cycle without correcting, at ``frequency`` [F, docs/state_estimation_nodes.rst]; Thrun, Burgard, Fox,
  Probabilistic Robotics 2005, Bayes/EKF filter chapters [K].
* Self-occlusion handled as no data, not a fault: MoveIt perception pipeline self-filtering removes the points that
  fall on the robot's own links (``padding_offset``/``padding_scale`` around the robot mesh) before the data is used
  [F; attached bodies not stated on the page read, 미확인]; Lippiello, Siciliano, Villani, eye-in-hand/eye-to-hand
  multi-camera visual servoing with an occlusion prediction that picks the cameras that see the features [S, search
  summary only].
* A held object blocking a wrist camera is a known case: EyeRobot 2.0, Hari et al., arXiv 2610.03710 (2026-10),
  active gaze beats wrist cameras (48 % vs 22 % success) when the grasped object occludes them [F abstract]; FingerViP,
  Zhang et al., arXiv 2604.21331: fingertip cameras against occlusion, wrist-camera occlusion by the hand and object
  stated in the search summary only [S]. Both change the sensor; we keep the camera and its field of view (AGENTS.md).
* Chaumette, Hutchinson, "Visual servo control" Parts I and II, IEEE RAM 2006/2007 [S]: Part II abstract read, it does
  not mention occlusion; the classical position that visibility loss must be handled by the controller, not by
  faulting, is not confirmed from the text (미확인).
What we took: no update on an occluded frame and continue from the own command model (Kalman / robot_localization),
with the own phase and own commands deciding that the view is blocked (self-filter idea, no ground truth). What we did
not take: a timeout that aborts after N occluded seconds (robot_localization's ``sensor_timeout`` is a predict-only
switch, not an abort); the phase barriers, ``LOCAL_TIMEOUT`` and the case cap already bound the loaded span.
"""
from __future__ import annotations

from harness import zone_pair_highpose_frame_gate as frame_gate
from harness.zone_pair_highpose_refix import DECIDE_STATE

PROFILE = 'zone_pair_own_load_occlusion_v1_v98'
VERSION = 'own_load_occlusion_v1'
VERDICT = 'OCCLUDED_BY_OWN_LOAD'
EVENT_START = 'own_image_occluded_by_own_load'
EVENT_END = 'own_image_occlusion_ended'
LOADED, RELEASE = 'loaded', 'release'
# Controller phases (run_m2_pair / study_owncam_pair_beam state names, plus the v98 sigma decision stop) in which the
# grip is closed on the beam. 'grasp' is not here: the receipt does not exist yet (the close has just been issued).
LOADED_PHASES = frozenset({'wait_lift', 'lift', 'wait_carry', 'carry', 'wait_lower', DECIDE_STATE, 'lower',
                           'wait_open'})
RELEASE_PHASES = frozenset({'cp_open', 'released'})


def record():
    return {'profile': PROFILE, 'version': VERSION, 'verdict': VERDICT, 'module': 'harness/zone_pair_highpose_own_load_occlusion.py',
            'events': [EVENT_START, EVENT_END], 'monitor_row_tag': {'own_image': VERDICT},
            'loaded_phases': sorted(LOADED_PHASES), 'release_phases': sorted(RELEASE_PHASES),
            'loaded_requires': 'own controller phase in loaded_phases AND own grasp receipt held '
                               '(beam_grasp_confirmed: current segment, issued gripper pulse closed)',
            'release_window': 'cp_open/released while the controller\'s own queued arm motion has not finished',
            'classified_when': 'frame fresh (<= 0.25 s), decodable, 480x640, and only the dark-fraction/contrast rule '
                               'fails (FrameGate.assess CONTENT_ONLY)',
            'effect': 'logged as no observation; the step continues from the own command history; no abort',
            'hard_stops_kept': ['stale, undecodable, wrong-shape or malformed frame in any phase',
                                'dark/uniform frame outside the loaded windows (INVALID_OWN_IMAGE)'],
            'inputs': 'own image, own issued commands (grasp receipt, queued arm motion), own controller phase',
            'not_inputs': 'ground truth, joint measurement, contact or success flags, shared top camera',
            'applies_in': 'formal and DEV runs alike (not a DEV soft stop; does not read DEV_LIGHT)',
            'max_occluded_duration_s': None,
            'gate_values_changed': False, 'frozen_modules_modified': False,
            'trigger_run': 'pair-llm-DEV-v103b-light-s911-8a1acdad-fast1 (INVALID_OWN_IMAGE at SIM 338.05)'}


class OwnLoadOcclusion:
    """One robot's occlusion classifier and record. ``ep`` is the v98 ``Execution``."""

    def __init__(self, execution):
        self.ep = execution
        self.episodes = []
        self.episode = None
        self.frame_ids = set()
        self._memo = None

    # ---- loaded window: own controller phase + own issued commands only ----
    def window(self, now):
        """``LOADED``, ``RELEASE`` or ``None``."""
        ctl = self.ep.controller
        state = ctl.state
        if state in LOADED_PHASES and bool(getattr(ctl, 'beam_grasp_confirmed', False)):
            return LOADED
        if state in RELEASE_PHASES:
            arm = ctl.arm
            if arm.events or now < arm.until - 1e-9:
                return RELEASE
        return None

    def _assess(self, now):
        ep = self.ep
        obs = ep.own.last_obs
        key = (None if not isinstance(obs, dict) else (obs.get('frame_id'), obs.get('sha256')), now)
        if self._memo is not None and self._memo[0] == key:
            return self._memo[1]
        gate = frame_gate.gate()
        out = gate.assess(obs, ep.own.robot_id, now, ob=bool(getattr(ep.policy, 'own_image_ob', False)))
        self._memo = (key, out)
        return out

    def accepts(self, now):
        """True when this tick's frame is ``VALID`` or ``OCCLUDED_BY_OWN_LOAD`` inside a loaded window.

        False leaves the verdict to the unchanged v98 gate: outside a window, and for a stale / undecodable /
        wrong-shape / malformed frame inside one.
        """
        ep = self.ep
        if ep.terminal:
            return False
        window = self.window(now)
        if window is None:
            self._end(now)
            return False
        verdict, measures = self._assess(now)
        if verdict == frame_gate.VALID:
            self._end(now)
            return True
        if verdict == frame_gate.CONTENT_ONLY:
            self._note(now, window, ep.own.last_obs, measures)
            return True
        return False

    # ---- record ----
    def _note(self, now, window, obs, measures):
        ep = self.ep
        fid = obs['frame_id']
        if self.episode is None:
            self.episode = {'start_s': now, 'end_s': None, 'window': window, 'phase': ep.controller.state,
                            'frames': 0, 'first_frame_id': fid, 'first_sha256': obs.get('sha256'),
                            'last_frame_id': None, 'last_sha256': None, 'last_s': now, 'measures_first': measures,
                            'phases': [ep.controller.state]}
            self.episodes.append(self.episode)
            ep.log(ep.own.robot_id, EVENT_START, now, verdict=VERDICT, window=window, phase=ep.controller.state,
                   frame_id=fid, sha256=obs.get('sha256'), **measures,
                   effect='no observation; commanded motion continues from own command history')
        episode = self.episode
        if fid != episode['last_frame_id']:
            episode['frames'] += 1
            episode['last_frame_id'], episode['last_sha256'] = fid, obs.get('sha256')
            self.frame_ids.add(fid)
        episode['last_s'] = now
        if ep.controller.state not in episode['phases']:
            episode['phases'].append(ep.controller.state)

    def _end(self, now):
        episode = self.episode
        if episode is None:
            return
        self.episode = None
        episode['end_s'] = now
        ep = self.ep
        ep.log(ep.own.robot_id, EVENT_END, now, verdict=VERDICT, start_s=episode['start_s'],
               duration_s=round(now-episode['start_s'], 4), frames=episode['frames'], phases=list(episode['phases']),
               last_frame_id=episode['last_frame_id'])

    def tag_row(self, row):
        """Extra fields of a grip-monitor row: the frame it reads was occluded by the own load."""
        return {'own_image': VERDICT} if row.get('frame_id') in self.frame_ids else {}

    def export(self):
        return {'profile': PROFILE, 'episodes': [dict(e, open_at_job_end=e['end_s'] is None) for e in self.episodes],
                'occluded_frames': sum(e['frames'] for e in self.episodes)}
