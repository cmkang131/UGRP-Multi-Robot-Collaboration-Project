"""render_cull_v1: output-exact frustum culling of the camera renders (execution-layer SPEED switch, DEFAULT off).

Why: the software (OSMesa) renderer draws every visible geom of the scene, also those far outside the camera's picture. A nine-robot map scene has
about 3500 of them; a robot camera (640x480) sees about 20 and a ceiling camera (1280x960) about 1400. Rendering is about 60 % of the wall clock
of a nine-robot run.

What: every `mujoco.Renderer.update_scene(data, camera)` call for a FIXED named camera first moves the geoms whose bounding sphere lies wholly
outside the camera's view frustum (or wholly behind it) into a geom group the scene option does not draw, builds the scene, and puts the groups back
(under one lock, the model is shared by all robots). Nothing the physics, the planner or the student reads is touched: only what is drawn.

Why the picture is identical (checked, not assumed): a geom outside the frustum cannot change a pixel as long as nothing in the scene reaches
from one pixel to another. That is true when no active light casts a shadow and no material that a geom uses reflects. This module checks both
facts on the model at the first render and, when either fails, does NOT cull (reason in the report; fail closed). Planes and height fields (no finite
bounding sphere) and geoms with `geom_rbound` 0 are never culled. The view frustum is the widest side of the camera's intrinsics, symmetric:
tan = (sensorsize / 2 + |principal point offset|) / focal * 1.02 per axis (without a sensor size: tan(fovy / 2) * 1.02 and the picture aspect), and the
bounding sphere gets 2 cm margin. The sign convention of the principal point does not matter for a symmetric bound.

verify=True renders every culled picture a second time from the FULL scene and compares the two pixel by pixel (slow: only for checks). A mismatch is
counted, the first few are described in the report, and the caller turns any mismatch into a failed run.

Needs only numpy (and mujoco, imported by install(), unless a module is handed in). Loaded BY FILE PATH by scripts/run_team_carry.py (the frozen scene
package replaces `harness` during a run), and only when --render-cull / --render-cull-verify is given; without the switch nothing of this file runs.
"""
from __future__ import annotations

import math
import sys
import threading

import numpy as np

HIDE_GROUPS = (5, 4, 3)     # candidate geom groups to park culled geoms in: the first one the scene option does not draw
MARGIN_M = 0.02             # added to every bounding-sphere radius
TAN_SLACK = 1.02            # widening of the view frustum
GEOM_PLANE, GEOM_HFIELD = 0, 1      # mjtGeom values (infinite / no bounding sphere); install() checks them against mujoco
MAX_MISMATCH_NOTES = 5


def camera_tans(sensorsize, intrinsic, fovy_deg, width, height):
    """(tan_x, tan_y): the tangent of the largest half view angle on each axis, conservative. A camera with MuJoCo intrinsics (sensor size > 0:
    focal fx fy and principal point offset ox oy, in length units like the sensor size) gets the widest side on each axis, (sensor / 2 + |offset|) / focal;
    other cameras fovy and the picture aspect."""
    if sensorsize[0] > 0 and sensorsize[1] > 0:
        fx, fy, ox, oy = (float(v) for v in intrinsic)
        return (float(sensorsize[0]) / 2 + abs(ox)) / fx * TAN_SLACK, (float(sensorsize[1]) / 2 + abs(oy)) / fy * TAN_SLACK
    ty = math.tan(math.radians(float(fovy_deg)) / 2) * TAN_SLACK
    return ty * width / height, ty


def cullable(geom_type, geom_rbound):
    """Mask of the geoms that may ever be culled: a finite bounding sphere, not a plane or a height field."""
    return (np.asarray(geom_rbound) > 0) & ~np.isin(np.asarray(geom_type), (GEOM_PLANE, GEOM_HFIELD))


def outside_frustum(geom_xpos, geom_rbound, cam_pos, cam_mat, tan_x, tan_y, margin=MARGIN_M):
    """Boolean array: True where the bounding sphere (centre geom_xpos, radius geom_rbound + margin) lies wholly outside the view frustum of a
    camera at cam_pos with the 3x3 frame cam_mat (columns x right, y up, z backwards: it looks along -z) or wholly behind it. Four side planes
    through the camera centre and the plane of the camera itself (nothing in front of the near plane is kept by this test)."""
    mat = np.asarray(cam_mat, float).reshape(3, 3)
    rel = np.asarray(geom_xpos, float) - np.asarray(cam_pos, float)
    cx, cy, cz = rel @ mat[:, 0], rel @ mat[:, 1], -(rel @ mat[:, 2])     # cz: depth in front of the camera
    r = np.asarray(geom_rbound, float) + margin
    nx, ny = math.sqrt(1 + tan_x * tan_x), math.sqrt(1 + tan_y * tan_y)
    return (((cx - tan_x * cz) / nx > r) | ((-cx - tan_x * cz) / nx > r)
            | ((cy - tan_y * cz) / ny > r) | ((-cy - tan_y * cz) / ny > r) | (cz < -r))


def guard_problem(model):
    """None when culling cannot change a pixel on this model, else the reason (a light that casts a shadow, a reflective material that a geom uses)."""
    active = np.asarray(model.light_active).astype(bool)
    if active.any() and np.asarray(model.light_castshadow).astype(bool)[active].any():
        return 'an active light casts a shadow'
    matid = np.asarray(model.geom_matid)
    used = np.unique(matid[matid >= 0])
    if used.size and (np.asarray(model.mat_reflectance)[used] > 0).any():
        return 'a material used by a geom is reflective'
    return None


class TopCardTiles:
    """Conservative visibility of the actual top-card geoms for the ceiling detector."""

    def __init__(self, model, cameras, robots, width, height):
        self.names = {name for name, _ in cameras}
        self.frusta = {}
        try:
            self.fallback = guard_problem(model)
            if self.fallback:
                return
            self.cards = [model.geom(rid + '__tag_top').id for rid in robots]
            if not self.cards or min(self.cards) < 0:
                raise ValueError('missing top card')
            self.radii = model.geom_rbound[self.cards].copy()
            if not np.all(np.isfinite(self.radii) & (self.radii > 0)):
                raise ValueError('unknown card radius')
            for name in self.names:
                cid = model.camera(name).id
                if model.cam_mode[cid] != 0 or any(getattr(model, attr)[cid] for attr in
                        ('cam_orthographic', 'cam_projection') if hasattr(model, attr)):
                    raise ValueError('unsupported ceiling projection')
                self.frusta[name] = (cid, *camera_tans(model.cam_sensorsize[cid], model.cam_intrinsic[cid],
                                                       model.cam_fovy[cid], width, height))
        except (AttributeError, IndexError, KeyError, ValueError, ZeroDivisionError) as exc:
            self.fallback = str(exc) or type(exc).__name__

    def needed(self, data):
        if self.fallback:
            return self.names
        centres = data.geom_xpos[self.cards]
        return {name for name, (cid, tx, ty) in self.frusta.items()
                if not outside_frustum(centres, self.radii, data.cam_xpos[cid], data.cam_xmat[cid], tx, ty).all()}


class RenderCull:
    """The patch of mujoco.Renderer.update_scene / render. install() / uninstall(); report() is a JSON-able dict."""

    def __init__(self, mujoco_module=None, verify=False):
        if mujoco_module is None:
            import mujoco as mujoco_module     # noqa: PLC0415 (only when the switch is on)
        self.mj = mujoco_module
        self.verify = bool(verify)
        self.lock = threading.RLock()
        self.models = {}            # id(model) -> (model, candidate mask or None, reason or None, geom_group snapshot at first sight)
        self.by_size = {}           # 'WxH' -> counters
        self.mismatches = 0
        self.compared = 0
        self.skipped = 0
        self.notes = []
        self.installed = False
        assert int(self.mj.mjtGeom.mjGEOM_PLANE) == GEOM_PLANE and int(self.mj.mjtGeom.mjGEOM_HFIELD) == GEOM_HFIELD
        self._orig_update = self._orig_render = None

    # ---- patch
    def install(self):
        R = self.mj.Renderer
        if getattr(R, '_render_cull_installed', False):
            raise RuntimeError('render_cull_v1 is already installed')
        self._orig_update, self._orig_render = R.update_scene, R.render
        cull = self

        def update_scene(renderer, *a, **k):
            return cull._update_scene(renderer, a, k)

        def render(renderer, *a, **k):
            return cull._render(renderer, a, k)

        R.update_scene, R.render, R._render_cull_installed = update_scene, render, True
        self.installed = True
        return self

    def uninstall(self):
        if self.installed:
            R = self.mj.Renderer
            R.update_scene, R.render = self._orig_update, self._orig_render
            R._render_cull_installed = False
            self.installed = False
        return self

    # ---- internals
    def _model_entry(self, m):
        entry = self.models.get(id(m))
        if entry is None or entry[0] is not m:
            reason = guard_problem(m)
            mask = None if reason else cullable(m.geom_type, m.geom_rbound)
            entry = self.models[id(m)] = (m, mask, reason, np.array(m.geom_group, copy=True))
        return entry

    def _counters(self, renderer):
        return self.by_size.setdefault('%dx%d' % (renderer.width, renderer.height),
                                       {'calls': 0, 'culled': 0, 'passthrough': 0, 'geoms_kept_sum': 0, 'geoms_hidden_sum': 0, 'geoms_full_sum': 0})

    def _plan(self, renderer, a, k):
        """(model, hide mask, hide group, option) for this update_scene call, or None when the call is passed through unchanged."""
        data = a[0] if a else k.get('data')
        camera = a[1] if len(a) > 1 else k.get('camera', -1)
        option = a[2] if len(a) > 2 else k.get('scene_option')
        if option is None:
            option = getattr(renderer, '_scene_option', None)
        m = getattr(renderer, '_model', None)
        if data is None or m is None or option is None or not isinstance(camera, (str, int)) or isinstance(camera, bool):
            return None
        _, mask, _reason, _ = self._model_entry(m)
        if mask is None:
            return None
        cid = self.mj.mj_name2id(m, self.mj.mjtObj.mjOBJ_CAMERA, camera) if isinstance(camera, str) else int(camera)
        if cid < 0 or cid >= m.ncam or int(m.cam_mode[cid]) != 0 or renderer.width * renderer.height <= 0:
            return None
        group = next((g for g in HIDE_GROUPS if int(option.geomgroup[g]) == 0), None)
        if group is None:
            return None
        tx, ty = camera_tans(m.cam_sensorsize[cid], m.cam_intrinsic[cid], m.cam_fovy[cid], renderer.width, renderer.height)
        hide = outside_frustum(data.geom_xpos, m.geom_rbound, data.cam_xpos[cid], data.cam_xmat[cid], tx, ty) & mask
        return m, hide, group

    def _update_scene(self, renderer, a, k):
        with self.lock:
            plan = self._plan(renderer, a, k)
            stats = self._counters(renderer)
            stats['calls'] += 1
            if plan is None:
                stats['passthrough'] += 1
                return self._orig_update(renderer, *a, **k)
            m, hide, group = plan
            if self.verify:      # the full scene first: its picture is what the culled picture must equal
                self._orig_update(renderer, *a, **k)
                renderer._render_cull_full = np.array(self._orig_render(renderer), copy=True)
            old = np.array(m.geom_group, copy=True)
            m.geom_group[hide] = group
            try:
                result = self._orig_update(renderer, *a, **k)
            finally:
                m.geom_group[:] = old
            stats['culled'] += 1
            stats['geoms_hidden_sum'] += int(hide.sum())
            stats['geoms_kept_sum'] += int(renderer.scene.ngeom)
            stats['geoms_full_sum'] += int(renderer.scene.ngeom) + int(hide.sum())
            return result

    def _render(self, renderer, a, k):
        result = self._orig_render(renderer, *a, **k)
        full = renderer.__dict__.pop('_render_cull_full', None)
        if full is not None:
            with self.lock:
                got = np.asarray(result)
                if got.shape != full.shape or got.dtype != full.dtype:
                    self.skipped += 1
                else:
                    self.compared += 1
                    if not np.array_equal(full, got):
                        self.mismatches += 1
                        diff = np.abs(full.astype(np.int64) - got.astype(np.int64))
                        note = {'size': '%dx%d' % (renderer.width, renderer.height), 'pixels_differing': int((diff.reshape(diff.shape[0], diff.shape[1], -1).max(-1) > 0).sum()),
                                'max_abs_diff': int(diff.max()), 'compared_so_far': self.compared}
                        if len(self.notes) < MAX_MISMATCH_NOTES:
                            self.notes.append(note)
                        print('RENDER_CULL_MISMATCH', note, file=sys.stderr, flush=True)
        return result

    # ---- report
    def report(self):
        guards = [{'reason': reason, 'ngeom': int(m.ngeom), 'cullable_geoms': None if mask is None else int(mask.sum()),
                   'geom_group_restored': bool((np.asarray(m.geom_group) == snap).all())} for m, mask, reason, snap in self.models.values()]
        return {'schema': 'render_cull_v1', 'verify': self.verify, 'installed': self.installed, 'models': guards,
                'by_size': {size: dict(c, geoms_kept_mean=(c['geoms_kept_sum'] / c['culled'] if c['culled'] else None),
                                       geoms_full_mean=(c['geoms_full_sum'] / c['culled'] if c['culled'] else None))
                            for size, c in self.by_size.items()},
                'verify_compared': self.compared, 'verify_mismatched': self.mismatches, 'verify_skipped_shape': self.skipped,
                'mismatch_notes': list(self.notes)}


def install(verify=False, mujoco_module=None):
    """Patch mujoco.Renderer and return the controller (call .uninstall() and .report() when the run is over)."""
    return RenderCull(mujoco_module, verify).install()
