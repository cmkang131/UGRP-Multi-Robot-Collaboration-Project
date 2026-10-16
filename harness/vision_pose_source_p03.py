"""Unregistered P03 v1 candidate (legacy provider bytes remain frozen): tag-free own-camera localization for the executor (issue #216).

Drop-in for ``harness.owncam_pose_source.OwnCamPoseSource`` (the ``tags_temporary`` provider of PR #229):
same duck-typed interface (``on_command``, ``on_frame``, ``report``, ``set_motion_profile``, ``source``,
``loc.estimate()`` / ``loc.predict_to()``), same ``PoseReport``.

* Measurement: PR #233's learned wall/door segmentation -> per-column interval observations, computed
  by the out-of-process torch worker (``harness.vision_loc_client``); the particle filter is PR #233's
  registered student (``vision_pf.make_robust_pf`` on the M1 PF, selected config v3), run in-process.
* Inputs: own wrist frames, own issued commands, own motion-profile switches, the static tag-free map
  and fixed calibrations (M1 motion model, VIS3 train camera sag/pan table). Nothing else.
* Prior: tag-free maps give no global fix, so the filter starts from ``init_prior`` (the own start dock
  from the scenario setup, +-15 cm / +-10 deg as in the VIS3 evaluation). Without a prior the provider
  stays ``initialized=False`` (the executor then never moves the base).
* ``since_tag_s`` of the report / estimate = SIM seconds since the last applied map measurement
  (tag-free analogue of "since the last tag fix"; the executor's look policy uses it).
* Fail closed: any worker failure (timeout, exit, broken pipe, malformed reply) ends localization for
  the episode: every later ``report()`` and ``loc.estimate()`` is ``initialized=False`` with the reason,
  so the executor's uncertainty gate stops base motion and no stale pose is used. A single refused or
  corrupted frame only skips that frame's measurement.
* Inference wall time is recorded (``timing``) and NOT charged to SIM time: the study cost model charges
  LLM thinking/talking only (#223, ``harness/zone_sim_cost.py``); in SYNC SIM physics waits for the reply.
"""
from __future__ import annotations

import copy
import math
import time
from collections.abc import Mapping, Sequence

import numpy as np

from harness import vision_loc_protocol as vp
from harness.vision_loc_contract_p03 import provider_runtime_contract
from harness.vision_pose_source import VisionPoseSource as LegacyVisionPoseSource
from harness.owncam_pose_source import PoseReport
from harness.vision_loc_client import FrameRejected, InProcessWorker, VisionWorkerClient, WorkerFailure

MAPS = ('zone_wide_door_walls_v3_notags',)
PRIOR_STD = (.15, .15, math.radians(10.))          # VIS3 dock prior (vision_loc_cli.DOCK_STD)


class FailClosedLoc:
    """The shared localizer seen by the executor's drivers; uninitialised once the provider failed."""

    def __init__(self, pf, provider_id=vp.PROVIDER_ID, *, on_command=None):
        self._pf = pf
        self._on_command = on_command or pf.command
        self.provider_id = provider_id
        self.failure: str | None = None

    def __getattr__(self, name):
        return getattr(self._pf, name)

    @property
    def initialized(self) -> bool:
        return self.failure is None and bool(self._pf.initialized)

    def predict_to(self, t: float) -> None:
        self._pf.predict_to(t)

    def command(self, row) -> None:
        # Legacy M2 calls loc.command; keep the owning source's servo/history
        # and lifecycle checks on that path as well.
        self._on_command(row)

    def estimate(self) -> dict:
        if self.failure is not None:
            return {'t': round(float(self._pf.t), 4), 'initialized': False, 'failure': self.failure}
        est = self._pf.estimate()
        if est.get('initialized'):
            last = self._pf.last_scan_t
            est['since_tag_s'] = None if last is None else round(float(self._pf.t) - float(last), 3)
            est['since_scan_s'] = est['since_tag_s']
            est.update(last_fix_t=last, fix_age_s=est['since_scan_s'], fix_source=self.provider_id)
        return est


def _finite_seq(values, n) -> bool:
    return isinstance(values, Sequence) and not isinstance(values, str) and len(values) == n and all(
        isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in values)


class VisionPoseSource(LegacyVisionPoseSource):
    """One robot's tag-free vision localizer (own frames + own commands -> ``PoseReport``)."""

    map_ids = MAPS
    map_file = vp.VIS3_DIR / 'maps' / 'zone_wide_door_walls_v3_notags.json'
    provider_id = 'vision_zero_tag_v1_p03_v1'
    source_prefix = 'owncam_pf_vision_zero_tag_v1_p03_v1'

    def __init__(self, static_map: Mapping, params: Mapping, seed: int = 0, *, worker=None, cfg=None):
        if not isinstance(seed, int) or isinstance(seed, bool):
            raise TypeError('seed must be an int')
        vl, vpf = vp.load_vis3()
        self.frozen = vp.check_frozen()
        mp = vl.mp
        m1_cal, self.m1_calibration = mp.load_m1_calibration()
        if vp.canonical(dict(params)) != vp.canonical(m1_cal['params']):
            raise ValueError('params differ from the M1 motion calibration the VIS3 student was scored with')
        vis3_map = vp.load_json(self.map_file)
        if static_map.get('map_id') not in self.map_ids or vp.canonical(dict(static_map)) != vp.canonical(vis3_map):
            raise ValueError(f'{self.provider_id} is registered for {self.map_ids} (the exact registered map) only, '
                             f'got {static_map.get("map_id")!r}')
        self.cfg = vp.load_config() if cfg is None else cfg
        self.runtime_contract = provider_runtime_contract(map_id=static_map['map_id'], cfg=self.cfg)
        sel = vp.selected_config()
        cal = vp.load_json(vp.VIS3_DIR / 'calibration_train.json')
        from harness.vision_motion_init import motion_module
        pf = vpf.make_robust_pf(motion_module(mp.load_m1_localizer()), copy.deepcopy(dict(static_map)), copy.deepcopy(dict(params)),
                                sel.get('measurement', {}), sel.get('obs', {}), cal['sag'], seed,
                                cal.get('pan_base_yaw') if sel.get('pan_coupling', True) else None,
                                sel.get('robust', {}))
        self.loc = FailClosedLoc(pf, self.provider_id, on_command=self.on_command)
        self.seed = seed
        identity = {'provider': self.provider_id, 'initialization_version': 2,
                    'runtime_contract_sha256': vp.sha256_bytes(vp.canonical(self.runtime_contract)),
                    'motion_init_sha256': vp.file_sha256(vp.ROOT / 'harness/vision_motion_init.py'), 'frozen': self.frozen, 'checkpoint_sha256': self.cfg['model']['sha256'],
                    'm1_calibration_sha256': self.m1_calibration['file_sha256'],
                    'map_sha256': vp.sha256_bytes(vp.canonical(dict(static_map)))}
        self.identity_sha256 = vp.sha256_bytes(vp.canonical(identity))
        self.source = f'{self.source_prefix}:{self.identity_sha256[:8]}'
        self.worker = worker if worker is not None else VisionWorkerClient(self.cfg)
        self.servo: dict[int, int] = {}
        self.prior: dict | None = None
        self.failure: dict | None = None
        self.last_obs: dict | None = None
        self.counts = {'frames': 0, 'worker_calls': 0, 'measured': 0, 'unsettled_or_uninitialized': 0,
                       'rejected_frames': 0, 'after_failure': 0}
        self.timing: list[dict] = []
        self.lifecycle: list[dict] = []
        self._started = False
        self._closed = False
        self._last_frame_t = None

    # ------------------------------------------------------------ inputs
    def begin_relocalization(self, now, servo):
        """Require a new scan without replacing vision with a different filter.

        A moving robot cannot reuse its episode-start dock as a current prior.
        Preserve the predicted belief and its uncertainty; invalidate only the
        previous fix receipt. A new accepted scan and the usual gates are needed.
        """
        self._check_clock(now)
        self._started = True
        self.loc.predict_to(now)
        previous_fix = self.loc._pf.last_scan_t
        self.loc._pf.last_scan_t = None
        self.last_obs = None
        # Servo/command history is already issued at the owning robot's port.
        # A relocalization request is not a new servo command or a PF reset.
        self.lifecycle.append({'event': 'begin_relocalization', 't': float(now),
                               'previous_fix_t': previous_fix, 'belief_preserved': True})

    def _check_clock(self, now):
        if self._closed:
            raise RuntimeError('vision pose provider is closed')
        if not isinstance(now, (int, float)) or isinstance(now, bool) or not math.isfinite(now) or now < 0:
            raise ValueError('provider time must be finite and nonnegative')
        if now < self.loc._pf.t - 1e-9:
            raise ValueError('provider clock must be monotonic')

    def expected_observability(self, pose, pan, static_map):
        """Visible static wall/door edge columns, using the frozen camera model.

        Ray casting accounts for static occlusion and the door gap. This is a
        heuristic proposal score, not calibrated information gain or a fix;
        no image inference, observation update or random draw is performed.
        """
        from harness.owncam_drive import LOOK_P20

        vl, _ = vp.load_vis3()
        geometry = vl.mp.MapGeometry(static_map, include_posts=False)
        camera = self.loc._pf.column_model_for({**LOOK_P20, 6: pan})
        rows = vl.expected_rows(geometry, np.array([[pose.x, pose.y, pose.yaw]]), camera)
        visible = [np.isfinite(r) & (r >= 1.) & (r < 479.) for r in rows]
        return float(sum(np.count_nonzero(v) for v in visible))

    def init_prior(self, mean: Sequence[float], std: Sequence[float] = PRIOR_STD, *, source: str) -> None:
        """Gaussian start prior from setup-only scenario facts (own dock); once, before the first frame."""
        if self._closed or self.prior is not None or self.counts['frames'] or self._started or self.loc._pf.t > 0:
            raise RuntimeError('the prior is set once, before the first own frame or runtime input')
        if not _finite_seq(mean, 3) or not _finite_seq(std, 3) or min(std) <= 0:
            raise ValueError('prior mean/std must be three finite numbers (std > 0)')
        if not isinstance(source, str) or not source:
            raise ValueError('prior needs a source description')
        self.loc._pf.init_gaussian(tuple(float(v) for v in mean), tuple(float(v) for v in std))
        self.prior = {'mean': [float(v) for v in mean], 'std': [float(v) for v in std], 'source': source,
                      'applied_sim_s': float(self.loc._pf.t), 'setup_only': True}

    def get_motion_params(self) -> dict:
        return copy.deepcopy(self.loc._pf._motion_params())

    def on_command(self, row: Mapping) -> None:
        """One own issued command (time ordered, as logged at the robot's port)."""
        self._check_clock(row['t'])
        if row['t'] > 0 or row['kind'] != 'initial_servo_command':
            self._started = True
        self.loc._pf.command(row)
        self.lifecycle.append({'event': 'own_command', 'row': copy.deepcopy(dict(row))})
        kind = row['kind']
        if kind == 'initial_servo_command':
            self.servo = {int(k): int(v) for k, v in row['pulses'].items()}
        elif kind == 'arm':
            self.servo[int(row['servo_id'])] = int(row['pulse'])
        elif kind == 'look':
            self.servo[6] = int(row['pan_pulse'])

    def set_motion_profile(self, now: float, name: str | None) -> None:
        self._check_clock(now)
        self._started = True
        if name != self.loc._pf.motion_profile:
            self.loc._pf.set_motion_profile(now, name)

    def on_frame(self, now: float, rgb) -> PoseReport:
        """One own ``robot_cam`` frame (RGB array decoded from the JPEG the robot saw)."""
        if not isinstance(now, (int, float)) or isinstance(now, bool) or not math.isfinite(now) or now < 0:
            raise ValueError(f'frame time must be a finite number, got {now!r}')
        if self._closed:
            raise RuntimeError('vision pose provider is closed')
        self.counts['frames'] += 1
        pf = self.loc._pf
        if now < pf.t - 1e-9 or (self._last_frame_t is not None and now <= self._last_frame_t):
            self.counts['rejected_frames'] += 1
            self.lifecycle.append({'event': 'rejected_frame', 't': float(now), 'reason': 'stale_or_duplicate'})
            return self.report(pf.t)
        self._last_frame_t = float(now)
        self._started = True
        if self.failure is not None:
            self.counts['after_failure'] += 1
            pf.predict_to(now)
            return self.report(now)
        obs = None
        if pf.initialized and pf.settled(now):
            try:
                bgr = np.ascontiguousarray(vp.check_frame(rgb)[..., ::-1])
            except vp.ProtocolError:
                bgr = None
                self.counts['rejected_frames'] += 1
            if bgr is not None:
                t0 = time.perf_counter()
                try:
                    self.counts['worker_calls'] += 1
                    obs = self.worker.observe(bgr)
                except FrameRejected:
                    self.counts['rejected_frames'] += 1
                except WorkerFailure as exc:
                    self._fail(now, str(exc))
                    pf.predict_to(now)
                    return self.report(now)
                worker_ms = 1000. * (time.perf_counter() - t0)
        else:
            self.counts['unsettled_or_uninitialized'] += 1
        t1 = time.perf_counter()
        est = pf.update_obs(now, obs, dict(self.servo))
        if obs is not None:
            self.timing.append({'t': round(float(now), 4), 'worker_ms': round(worker_ms, 3),
                                'pf_ms': round(1000. * (time.perf_counter() - t1), 3)})
            if est.get('measured'):
                self.counts['measured'] += 1
                self.last_obs = {'t': round(float(now), 4), 'n_cols': int(obs.informative.sum())}
        return self.report(now)

    def _fail(self, now: float, reason: str) -> None:
        self.failure = {'t': round(float(now), 4), 'reason': reason[:500]}
        self.loc.failure = f'vision worker failed at {self.failure["t"]} s: {reason[:200]}'
        try:
            self.worker.close()
        except Exception as exc:  # noqa: BLE001 - recorded; the provider stays failed closed either way
            self.failure['close_error'] = f'{type(exc).__name__}: {exc}'[:200]

    # ------------------------------------------------------------ outputs
    def report(self, now: float) -> PoseReport:
        self._check_clock(now)
        self._started |= now > 0
        pf = self.loc._pf
        pf.predict_to(now)
        load = 'loaded' if pf.load.loaded else 'unloaded'
        est = self.loc.estimate()
        if not est.get('initialized'):
            return PoseReport(t_est=float(now), initialized=False, load_state=load, source=self.source,
                              last_valid_obs=self.last_obs, fix_source=self.provider_id,
                              observation_quality={'accepted': False, 'failure': self.failure})
        return PoseReport(t_est=float(est['t']), initialized=True, x_m=est['x'], y_m=est['y'], yaw_rad=est['yaw'],
                          cov=tuple(tuple(r) for r in est['cov']), std_xy_m=est['std_xy_m'],
                          std_yaw_rad=est['std_yaw_rad'], since_tag_s=est.get('since_tag_s'),
                          last_valid_obs=self.last_obs, n_eff=round(float(est['n_eff']), 1), load_state=load,
                          source=self.source, last_fix_t=est['last_fix_t'], fix_age_s=est['fix_age_s'],
                          fix_source=self.provider_id,
                          observation_quality={'accepted': est['last_fix_t'] == now,
                                               'informative_columns': 0 if self.last_obs is None else self.last_obs['n_cols'],
                                               'diagnostics': copy.deepcopy(pf.diag)})

    def record(self) -> dict:
        ms = sorted(r['worker_ms'] for r in self.timing)
        pct = (lambda q: None if not ms else ms[min(len(ms) - 1, int(q * len(ms)))])
        return {'provider': self.provider_id, 'source': self.source, 'identity_sha256': self.identity_sha256,
                'frozen_files_sha256': self.frozen, 'm1_calibration': self.m1_calibration, 'prior': self.prior,
                'seed': self.seed, 'counts': dict(self.counts), 'failure': self.failure,
                'worker': self.worker.record(), 'localizer_stats': dict(self.loc._pf.stats),
                'inference_wall_ms': {'n': len(ms), 'p50': pct(.5), 'p90': pct(.9), 'max': ms[-1] if ms else None},
                'sim_time_charge': dict(self.cfg['sim_time_charge']), 'runtime_contract': copy.deepcopy(self.runtime_contract),
                'applied_perception_delay_s': 0., 'delay_owner': 'outer DelayedPoseSource in StudyTeamHost',
                'closed': self._closed,
                'lifecycle': copy.deepcopy(self.lifecycle)}

    def close(self) -> None:
        if not self._closed:
            self.loc.failure = self.loc.failure or 'vision pose provider closed'
            try:
                self.worker.close()
            finally:
                self._closed = True


__all__ = ['VisionPoseSource', 'FailClosedLoc', 'InProcessWorker', 'MAPS', 'PRIOR_STD']


class VisionPoseSourceV2(VisionPoseSource):
    """Registered geometry-only map + measurement-free PF initialization, unscored."""
    map_ids = ('zone_wide_door_geometry_v2',)
    map_file = vp.ROOT / 'maps/zones/zone_wide_door_geometry_v2.json'
    provider_id = 'vision_zero_tag_v2_p03_v1'
    source_prefix = 'owncam_pf_vision_zero_tag_v2_p03_v1'
