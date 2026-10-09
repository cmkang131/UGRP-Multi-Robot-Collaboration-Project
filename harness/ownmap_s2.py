"""Default-off, OFFLINE-ONLY S2 localization map adapter.

Own start frame; no truth, map registration or source pose/particle prior.
Nav2's occupied-cell distance field / free-cell uniform initialization, as
already used in claude/ego-wall-map's self_map_relocalize.GridField. The frozen
S2 camera, motion, KLD, measurement and report implementations are reused.
No module globals are patched and the full transport controller is disabled.
"""
from __future__ import annotations

import copy
import math
from dataclasses import asdict
from types import SimpleNamespace

import numpy as np
from scipy.ndimage import distance_transform_edt

OPTION = 'own_grid_v1'
FRAME = 'own start chassis: x forward, y left, metres'


def convert(grid, goal=None, *, option='off'):
    """Return None when disabled; never inspect an off input."""
    if option == 'off':
        return None
    if option != OPTION:
        raise ValueError('UNKNOWN_OWNMAP_OPTION')
    if grid.get('frame') != FRAME:
        raise ValueError('OWN_START_FRAME_REQUIRED')
    cells = np.asarray(grid['cells'], dtype=float)
    res = float(grid['resolution_m'])
    if (cells.ndim != 2 or cells.shape[1] != 3 or not len(cells)
            or not np.isfinite(cells).all() or not math.isfinite(res) or res <= 0
            or not np.equal(cells[:, :2], np.floor(cells[:, :2])).all()):
        raise ValueError('FINITE_INTEGER_GRID_REQUIRED')
    if len(np.unique(cells[:, :2], axis=0)) != len(cells):
        raise ValueError('DUPLICATE_GRID_CELL')
    if not (cells[:, 2] > 0).any() or not (cells[:, 2] < 0).any():
        raise ValueError('OCCUPIED_AND_OBSERVED_FREE_REQUIRED')
    lo = cells[:, :2].min(0)*res
    hi = (cells[:, :2].max(0)+1)*res
    # Lossless horizontal runs, solely for the legacy geometry constructor.
    # No height was observed; zero is a placeholder. Only the grid field is
    # queried by the admitted offline sensor path, never this 3D geometry.
    obstacles = []
    occupied = cells[cells[:, 2] > 0, :2].astype(int)
    for y in np.unique(occupied[:, 1]):
        xs = np.sort(occupied[occupied[:, 1] == y, 0])
        for run in np.split(xs, np.flatnonzero(np.diff(xs) > 1)+1):
            obstacles.append(dict(kind='wall', id=f'own-{len(obstacles)}',
                center_m=[float((run[0]+run[-1]+1)*res/2), float((y+.5)*res)],
                half_extents_m=[float(len(run)*res/2), res/2], height_m=0.,
                height_observed=False, yaw_rad=0.))
    regions = {}
    if goal is not None:
        if goal.get('source') != 'own' or goal.get('entity', {}).get('kind') != 'floor_zone':
            raise ValueError('OWN_OBSERVED_FLOOR_GOAL_REQUIRED')
        box = np.asarray(goal['bounds_m'], float)
        if box.shape != (2, 2) or not np.isfinite(box).all() or (box[1] < box[0]).any():
            raise ValueError('INVALID_OBSERVED_FLOOR_EXTENT')
        regions[goal['entity']['id']] = {k: copy.deepcopy(goal[k]) for k in (
            'entity', 'center_m', 'bounds_m', 'partial_extent', 'source', 'detector',
            'frame_sha256', 'first_t', 't_sim', 'observations') if k in goal}
        regions[goal['entity']['id']]['boundary_observed'] = False
    return dict(schema='ugrp.ownmaps2a.static.v1', map_id='ownmaps2a', frame=FRAME,
        bounds_m=[float(lo[0]), float(hi[0]), float(lo[1]), float(hi[1])],
        obstacles=obstacles, occupancy_grid=dict(resolution_m=res, cells=cells.tolist()),
        regions={}, observed_regions=regions, observed_floor_edges=[], passages=[],
        pickup_slots=[], zone_slots={}, landmarks={'tags': [], 'door_posts': []}, terrain=[],
        missing=['verified_floor_boundaries', 'complete_floor_regions', 'door_entities',
                 'pickup_slots', 'delivery_slots', 'wall_height', 'unobserved_space'],
        gt_inputs=False, start_prior='none_v1', transport_admitted=False)


class GridField:
    """Cell-center EDT at the frozen S2 1cm resolution (no wall snapping)."""
    def __init__(self, static):
        from harness.zone_solo_cyan_likelihood_field import PARAMS
        self.res = PARAMS['grid_resolution_m']
        g = static['occupancy_grid']; self.grid_resolution = float(g['resolution_m'])
        factor = round(self.grid_resolution/self.res)
        if factor < 1 or abs(factor*self.res-self.grid_resolution) > 1e-9:
            raise ValueError('AMCL_GRID_RESOLUTION_MULTIPLE')
        cells = np.asarray(g['cells'], float); ij = cells[:, :2].astype(int)
        self.lo = ij.min(0)-10; hi = ij.max(0)+11
        shape = tuple((hi-self.lo)[::-1])
        if np.prod(shape)*factor**2 > 20_000_000:
            raise ValueError('GRID_RASTER_BUDGET')
        self.raw = np.full(shape, 255, np.uint8)
        x, y = (ij-self.lo).T
        self.raw[y, x] = np.where(cells[:, 2] > 0, 254, np.where(cells[:, 2] < 0, 0, 255))
        occupied = np.repeat(np.repeat(self.raw == 254, factor, 0), factor, 1)
        self.grid_origin = self.lo*self.grid_resolution
        self.origin = self.grid_origin+self.res/2
        self.shape = occupied.shape
        self.dist = np.minimum(distance_transform_edt(~occupied)*self.res, PARAMS['max_occ_dist_m'])
        self.free_cells = ij[cells[:, 2] < 0]

    def distances(self, points):
        from harness.zone_solo_cyan_likelihood_field import Field
        return Field.distances(self, points)

    def uniform(self, rng, n):
        cells = self.free_cells[rng.integers(len(self.free_cells), size=n)]
        xy = (cells+rng.random((n, 2)))*self.grid_resolution
        return np.c_[xy, rng.uniform(-math.pi, math.pi, n)]

    def free(self, xy):
        ij = np.floor(np.asarray(xy)/self.grid_resolution).astype(int)-self.lo
        x, y = ij.T
        ok = (x >= 0) & (y >= 0) & (x < self.raw.shape[1]) & (y < self.raw.shape[0])
        out = np.zeros(len(x), bool)
        out[ok] = self.raw[y[ok], x[ok]] == 0
        return out


def _forbid_control(*args, **kwargs):
    raise RuntimeError('OWNMAP_S2_OFFLINE_LOCALIZATION_ONLY')


def build_runtime(bundle, static, calibration, calibration_sha, *, option='off'):
    """No simulator, GT or task geometry accepted by the opt-in constructor.

    Fixed calibration is validated using its original admission metadata, then
    transferred unchanged. Local private function bindings permit a different
    map; the production S2 admission/constructors remain byte-identical.
    """
    from scripts.run_s2_unknown_start import runtime_factory
    plain = copy.deepcopy(bundle)
    active = plain['options'].pop('active_localization', 'off')
    if option == 'off':
        rt = runtime_factory(plain)(static, calibration, calibration_sha, **plain['task'])
    elif option == OPTION:
        if static.get('schema') != 'ugrp.ownmaps2a.static.v1' or static.get('gt_inputs') is not False:
            raise ValueError('OWNMAP_ADAPTER_OUTPUT_REQUIRED')
        from harness import zone_solo_cyan_v106 as legacy
        from harness import vision_pose_source_highpose as high
        from harness.zone_final_pair_binding import bind
        from harness.zone_solo_cyan_unknown_start import _NoDockInitialization
        from harness.zone_solo_cyan_kld_start import Runtime as KLD
        from harness.zone_solo_cyan_look_ahead import Runtime as Carry
        from harness.zone_solo_cyan_best_cluster import runtime_class as best
        from harness.zone_solo_cyan_amcl_sensor import runtime_class as sensor
        from harness.zone_solo_cyan_landmarks import runtime_class as landmarks
        from harness.zone_solo_cyan_bias_tempering import closure, replace_cell

        field = GridField(static)
        admitted = high.contract.admitted_calibration(calibration, calibration_sha,
                                                      'zone_wide_door_geometry_v3')
        contract = SimpleNamespace(**vars(high.contract))
        contract.resolve = lambda map_id: (static, None, None)
        contract.admitted_calibration = lambda *a: copy.deepcopy(admitted)
        source_init = bind(high.HighPoseSource.__init__, contract=contract)

        class Source(high.HighPoseSource):
            def __init__(self, *a, **kw):
                source_init(self, *a, **kw)
                from harness import vision_loc_protocol as vp
                legacy.partial.install(self.loc._pf, vp.load_vis3()[0])
                pf = self.loc._pf
                pf._uniform_free = lambda n: field.uniform(pf.rng, n)
                pf._map_logprior = lambda px: np.where(field.free(px[:, :2]), 0.,
                    pf.params['map']['wall_log_penalty'])
                self.runtime_contract['own_map'] = dict(schema=static['schema'], frame=static['frame'],
                    map_sha256=legacy.hp.base.digest(static), gt_inputs=False, option=OPTION)

        partial = SimpleNamespace(**vars(legacy.partial))
        partial.build_source_class = lambda: Source
        provider = bind(legacy.build_provider, partial=partial)
        from harness import zone_solo_cyan_camera_v3 as camera
        camera_legacy = SimpleNamespace(**vars(legacy))
        camera_legacy.build_provider = provider
        provider = bind(camera.build_provider, legacy=camera_legacy)
        provider.controller_geometry_id = legacy.build_provider.controller_geometry_id
        provider.uses_landmark_tags = False
        # Reuse the frozen task-independent initialization. Task metadata is
        # intentionally absent, and control entry points below always raise.
        taskless = SimpleNamespace(**vars(legacy))
        taskless.passage_route = lambda *a: []
        taskless.pickup_slots = lambda *a: {plain['task']['pickup_slot']: None}
        initialize = bind(_NoDockInitialization.__init__, legacy=taskless)

        class Taskless(_NoDockInitialization):
            def __init__(self, local_map, *a, **kw):
                # The frozen constructor checks a legacy map name only. The
                # supplied dict and provider still contain only own geometry.
                local = copy.deepcopy(local_map)
                local['map_id'] = 'zone_wide_door_geometry_v3'
                # Match exact private resolve to this same dict, no disk map.
                contract.resolve = lambda map_id: (local, None, None)
                initialize(self, local, *a, **kw)
                self.map['map_id'] = 'ownmaps2a'

        class Localizer(KLD, Carry, Taskless):
            pass

        Runtime = landmarks(sensor(best(Localizer)))
        omit = ('drive_profile', 'stagnation_watch', 'idle_robot_contacts', 'dev_grasp_policy', 'eval_camera_trace')
        options = {k: v for k, v in plain['options'].items() if k not in omit}
        keys = ('motion_model', 'pulse_calibration', 'extrinsic_calibration', 'floor_appearance',
                'stiff_camera_table', 'look_ahead_calibration')
        rt = Runtime(static, calibration, calibration_sha, provider_factory=provider, **plain['task'], **options,
                     **{k: plain[k] for k in keys})
        pf = rt.pose.provider.loc._pf
        selected = closure(pf.update_obs)['selected']
        selected = replace_cell(selected, 'field', field)
        pf.update_obs = replace_cell(pf.update_obs, 'selected', selected)
        rt.own_map_field = field
    else:
        raise ValueError('UNKNOWN_OWNMAP_OPTION')
    if active != 'off':
        from harness.zone_solo_cyan_active_observation import attach
        rt = attach(rt, active_localization=active)
    # Fixed command replay only: never plan a path, new observation, or action.
    rt.step = rt.drive = rt._control = _forbid_control
    return rt


def report_row(report, now):
    q = asdict(report)
    return dict(t=now, t_est=q['t_est'], x=q['x_m'], y=q['y_m'], yaw=q['yaw_rad'],
        std_xy_m=q['std_xy_m'], std_yaw_rad=q['std_yaw_rad'], last_fix_t=q['last_fix_t'],
        initialized=q['initialized'], cov=q['cov'], observation_quality=q['observation_quality'])


def warned(row):
    modes = (row.get('observation_quality') or {}).get('diagnostics', {}).get('pose_estimate', {})
    return bool(not row.get('initialized', True) or row['std_xy_m'] > .05 or
        row['std_yaw_rad'] > math.radians(5) or row['last_fix_t'] is None or modes.get('uncertain', False))
