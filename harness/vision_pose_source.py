"""Pose provider ``vision_zero_tag_v1``: tag-free own-camera localization for the executor (issue #216).

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
from harness.owncam_pose_source import PoseReport
from harness.vision_loc_client import FrameRejected, InProcessWorker, VisionWorkerClient, WorkerFailure

MAPS = ('zone_wide_door_walls_v3_notags',)
PRIOR_STD = (.15, .15, math.radians(10.))          # VIS3 dock prior (vision_loc_cli.DOCK_STD)


class FailClosedLoc:
    """The shared localizer seen by the executor's drivers; uninitialised once the provider failed."""

    def __init__(self, pf):
        self._pf = pf
        self.failure: str | None = None

    def __getattr__(self, name):
        return getattr(self._pf, name)

    @property
    def initialized(self) -> bool:
        return self.failure is None and bool(self._pf.initialized)

    def predict_to(self, t: float) -> None:
        self._pf.predict_to(t)

    def estimate(self) -> dict:
        if self.failure is not None:
            return {'t': round(float(self._pf.t), 4), 'initialized': False, 'failure': self.failure}
        est = self._pf.estimate()
        if est.get('initialized'):
            last = self._pf.last_scan_t
            est['since_tag_s'] = None if last is None else round(float(self._pf.t) - float(last), 3)
            est['since_scan_s'] = est['since_tag_s']
        return est


def _finite_seq(values, n) -> bool:
    return isinstance(values, Sequence) and not isinstance(values, str) and len(values) == n and all(
        isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in values)


class VisionPoseSource:
    """One robot's tag-free vision localizer (own frames + own commands -> ``PoseReport``)."""

    def __init__(self, static_map: Mapping, params: Mapping, seed: int = 0, *, worker=None, cfg=None):
        if not isinstance(seed, int) or isinstance(seed, bool):
            raise TypeError('seed must be an int')
        vl, vpf = vp.load_vis3()
        self.frozen = vp.check_frozen()
        mp = vl.mp
        m1_cal, self.m1_calibration = mp.load_m1_calibration()
        if vp.canonical(dict(params)) != vp.canonical(m1_cal['params']):
            raise ValueError('params differ from the M1 motion calibration the VIS3 student was scored with')
        vis3_map = vp.load_json(vp.VIS3_DIR / 'maps' / 'zone_wide_door_walls_v3_notags.json')
        if static_map.get('map_id') not in MAPS or vp.canonical(dict(static_map)) != vp.canonical(vis3_map):
            raise ValueError(f'vision_zero_tag_v1 is registered for {MAPS} (the VIS3 map file) only, '
                             f'got {static_map.get("map_id")!r}')
        self.cfg = vp.load_config() if cfg is None else cfg
        sel = vp.selected_config()
        cal = vp.load_json(vp.VIS3_DIR / 'calibration_train.json')
        pf = vpf.make_robust_pf(mp.load_m1_localizer(), copy.deepcopy(dict(static_map)), copy.deepcopy(dict(params)),
                                sel.get('measurement', {}), sel.get('obs', {}), cal['sag'], seed,
                                cal.get('pan_base_yaw') if sel.get('pan_coupling', True) else None,
                                sel.get('robust', {}))
        self.loc = FailClosedLoc(pf)
        self.seed = seed
        identity = {'provider': vp.PROVIDER_ID, 'frozen': self.frozen, 'checkpoint_sha256': self.cfg['model']['sha256'],
                    'm1_calibration_sha256': self.m1_calibration['file_sha256']}
        self.identity_sha256 = vp.sha256_bytes(vp.canonical(identity))
        self.source = f'{vp.SOURCE_LABEL_PREFIX}:{self.identity_sha256[:8]}'
        self.worker = worker if worker is not None else VisionWorkerClient(self.cfg)
        self.servo: dict[int, int] = {}
        self.prior: dict | None = None
        self.failure: dict | None = None
        self.last_obs: dict | None = None
        self.counts = {'frames': 0, 'worker_calls': 0, 'measured': 0, 'unsettled_or_uninitialized': 0,
                       'rejected_frames': 0, 'after_failure': 0}
        self.timing: list[dict] = []

    # ------------------------------------------------------------ inputs
    def init_prior(self, mean: Sequence[float], std: Sequence[float] = PRIOR_STD, *, source: str) -> None:
        """Gaussian start prior from setup-only scenario facts (own dock); once, before the first frame."""
        if self.prior is not None or self.counts['frames']:
            raise RuntimeError('the prior is set once, before the first own frame')
        if not _finite_seq(mean, 3) or not _finite_seq(std, 3) or min(std) <= 0:
            raise ValueError('prior mean/std must be three finite numbers (std > 0)')
        if not isinstance(source, str) or not source:
            raise ValueError('prior needs a source description')
        self.loc._pf.init_gaussian(tuple(float(v) for v in mean), tuple(float(v) for v in std))
        self.prior = {'mean': [float(v) for v in mean], 'std': [float(v) for v in std], 'source': source}

    def on_command(self, row: Mapping) -> None:
        """One own issued command (time ordered, as logged at the robot's port)."""
        self.loc._pf.command(row)
        kind = row['kind']
        if kind == 'initial_servo_command':
            self.servo = {int(k): int(v) for k, v in row['pulses'].items()}
        elif kind == 'arm':
            self.servo[int(row['servo_id'])] = int(row['pulse'])
        elif kind == 'look':
            self.servo[6] = int(row['pan_pulse'])

    def set_motion_profile(self, now: float, name: str | None) -> None:
        if name != self.loc._pf.motion_profile:
            self.loc._pf.set_motion_profile(now, name)

    def on_frame(self, now: float, rgb) -> PoseReport:
        """One own ``robot_cam`` frame (RGB array decoded from the JPEG the robot saw)."""
        if not isinstance(now, (int, float)) or isinstance(now, bool) or not math.isfinite(now):
            raise ValueError(f'frame time must be a finite number, got {now!r}')
        self.counts['frames'] += 1
        pf = self.loc._pf
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
        pf = self.loc._pf
        pf.predict_to(now)
        load = 'loaded' if pf.load.loaded else 'unloaded'
        est = self.loc.estimate()
        if not est.get('initialized'):
            return PoseReport(t_est=float(now), initialized=False, load_state=load, source=self.source,
                              last_valid_obs=self.last_obs)
        return PoseReport(t_est=float(est['t']), initialized=True, x_m=est['x'], y_m=est['y'], yaw_rad=est['yaw'],
                          cov=tuple(tuple(r) for r in est['cov']), std_xy_m=est['std_xy_m'],
                          std_yaw_rad=est['std_yaw_rad'], since_tag_s=est.get('since_tag_s'),
                          last_valid_obs=self.last_obs, n_eff=round(float(est['n_eff']), 1), load_state=load,
                          source=self.source)

    def record(self) -> dict:
        ms = sorted(r['worker_ms'] for r in self.timing)
        pct = (lambda q: None if not ms else ms[min(len(ms) - 1, int(q * len(ms)))])
        return {'provider': vp.PROVIDER_ID, 'source': self.source, 'identity_sha256': self.identity_sha256,
                'frozen_files_sha256': self.frozen, 'm1_calibration': self.m1_calibration, 'prior': self.prior,
                'seed': self.seed, 'counts': dict(self.counts), 'failure': self.failure,
                'worker': self.worker.record(), 'localizer_stats': dict(self.loc._pf.stats),
                'inference_wall_ms': {'n': len(ms), 'p50': pct(.5), 'p90': pct(.9), 'max': ms[-1] if ms else None},
                'sim_time_charge': dict(self.cfg['sim_time_charge'])}

    def close(self) -> None:
        self.worker.close()


__all__ = ['VisionPoseSource', 'FailClosedLoc', 'InProcessWorker', 'MAPS', 'PRIOR_STD']
