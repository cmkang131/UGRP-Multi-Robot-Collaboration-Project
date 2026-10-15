"""Explicit experimental camera sampling profiles; native K/D/mount unchanged.

No default consumer is changed. Call configure_model BEFORE creating a renderer,
then configure_context on its owning GL thread. Only framebuffer quality changes.
See experiments/2026-10-16-scene-tex3 for sources and measured costs.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import cv2
import numpy as np

from sim.masterpi_camera_profile import raw_fisheye_remap


@dataclass(frozen=True)
class Quality:
    scale: int = 1
    samples: int | None = None
    interpolation: str = 'linear'
    min_filter: str = 'trilinear'


# 2x is the user's supersampling example, 8 samples is a requested comparison,
# not a quality acceptance threshold. Drivers may clamp it (record actual).
PROFILES = {
    'native': Quality(),
    'ss2_area_v1': Quality(scale=2),
    'msaa8_v1': Quality(samples=8),
    'cubic_v1': Quality(interpolation='cubic'),
    'mip_nearest_v1': Quality(min_filter='nearest_mip'),
    'no_mip_v1': Quality(min_filter='linear'),
}


def resolve(name):
    if name not in PROFILES:
        raise ValueError('unknown camera quality profile: ' + str(name))
    return PROFILES[name]


def configure_model(model, name, width=640, height=480):
    q = resolve(name)
    model.vis.global_.offwidth = max(model.vis.global_.offwidth, width * q.scale)
    model.vis.global_.offheight = max(model.vis.global_.offheight, height * q.scale)
    if q.samples is not None:
        model.vis.quality.offsamples = q.samples
    return width * q.scale, height * q.scale


def configure_context(renderer, model, name):
    """Query actual GL state, optionally change minification on this context."""
    from OpenGL import GL
    q = resolve(name)
    renderer._gl_context.make_current()
    ctx = renderer._mjr_context
    rows = []
    GL.glActiveTexture(GL.GL_TEXTURE0)
    for i in range(model.ntex):
        target = GL.GL_TEXTURE_2D if int(model.tex_type[i]) == 0 else GL.GL_TEXTURE_CUBE_MAP
        GL.glBindTexture(target, int(ctx.texture[i]))
        before = int(GL.glGetTexParameteriv(target, GL.GL_TEXTURE_MIN_FILTER))
        if q.min_filter != 'trilinear':
            value = GL.GL_LINEAR_MIPMAP_NEAREST if q.min_filter == 'nearest_mip' else GL.GL_LINEAR
            GL.glTexParameteri(target, GL.GL_TEXTURE_MIN_FILTER, value)
        rows.append({'id': i, 'before_min': before,
                     'min': int(GL.glGetTexParameteriv(target, GL.GL_TEXTURE_MIN_FILTER)),
                     'mag': int(GL.glGetTexParameteriv(target, GL.GL_TEXTURE_MAG_FILTER)),
                     'base_width': int(GL.glGetTexLevelParameteriv(
                         GL.GL_TEXTURE_2D if target == GL.GL_TEXTURE_2D else GL.GL_TEXTURE_CUBE_MAP_POSITIVE_X,
                         0, GL.GL_TEXTURE_WIDTH))})
    GL.glBindTexture(GL.GL_TEXTURE_2D, 0)
    GL.glBindTexture(GL.GL_TEXTURE_CUBE_MAP, 0)
    return {'profile': name, 'definition': asdict(q),
            'offwidth': int(model.vis.global_.offwidth), 'offheight': int(model.vis.global_.offheight),
            'requested_samples': int(model.vis.quality.offsamples), 'actual_samples': int(ctx.offSamples),
            'max_samples': int(GL.glGetIntegerv(GL.GL_MAX_SAMPLES)), 'textures': rows}


def sampling_stages(ideal, name, width=640, height=480):
    """Same lens geometry at high resolution, then area reduction to native.

    OpenCV remap uses inverse maps. K scales with source AND destination; no
    extra crop, new FOV, sharpening, or camera movement is introduced.
    """
    q = resolve(name)
    if ideal.shape != (height*q.scale, width*q.scale, 3):
        raise ValueError('unexpected pinhole render size')
    mx, my = raw_fisheye_remap(width*q.scale, height*q.scale)
    method = cv2.INTER_LINEAR if q.interpolation == 'linear' else cv2.INTER_CUBIC
    raw = cv2.remap(ideal, mx, my, method, borderMode=cv2.BORDER_CONSTANT)
    final = cv2.resize(raw, (width, height), interpolation=cv2.INTER_AREA) if q.scale != 1 else raw
    return {'pinhole': ideal, 'fisheye': raw, 'final': final}


def remap_ids(ids, name, width=640, height=480):
    """Evaluation labels only; never interpolate integer IDs."""
    q = resolve(name)
    mx, my = raw_fisheye_remap(width*q.scale, height*q.scale)
    raw = cv2.remap(ids.astype(np.float32), mx, my, cv2.INTER_NEAREST,
                    borderMode=cv2.BORDER_CONSTANT, borderValue=-1)
    return cv2.resize(raw, (width, height), interpolation=cv2.INTER_NEAREST).astype(np.int32)
