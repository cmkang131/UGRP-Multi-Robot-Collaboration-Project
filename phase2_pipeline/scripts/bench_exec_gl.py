"""Identify the software GL path and compare 640x480 RGB readbacks without a physics dependency."""
from contextlib import contextmanager
import ctypes
import hashlib
import json
import os
from statistics import median
from time import perf_counter

import numpy as np
from OpenGL import GL


@contextmanager
def context(width, height):
    backend = os.environ['PYOPENGL_PLATFORM']
    if backend == 'osmesa':
        from OpenGL import osmesa
        ctx = osmesa.OSMesaCreateContextExt(osmesa.OSMESA_RGBA, 24, 0, 0, None)
        pixels = np.empty((height, width, 4), np.uint8)
        try:
            if not osmesa.OSMesaMakeCurrent(ctx, pixels, GL.GL_UNSIGNED_BYTE, width, height):
                raise RuntimeError('OSMesa context creation failed')
            yield
        finally:
            osmesa.OSMesaDestroyContext(ctx)
    elif backend == 'egl':
        from OpenGL import EGL as e
        display = e.eglGetDisplay(e.EGL_DEFAULT_DISPLAY)
        e.eglInitialize(display, None, None)
        try:
            e.eglBindAPI(e.EGL_OPENGL_API)
            attrs = [e.EGL_SURFACE_TYPE, e.EGL_PBUFFER_BIT, e.EGL_RENDERABLE_TYPE, e.EGL_OPENGL_BIT,
                     e.EGL_RED_SIZE, 8, e.EGL_GREEN_SIZE, 8, e.EGL_BLUE_SIZE, 8, e.EGL_DEPTH_SIZE, 24, e.EGL_NONE]
            configs, count = (e.EGLConfig * 1)(), e.EGLint()
            e.eglChooseConfig(display, attrs, configs, 1, ctypes.byref(count))
            if not count.value:
                raise RuntimeError('no EGL desktop GL pbuffer configuration')
            surface = e.eglCreatePbufferSurface(display, configs[0], [e.EGL_WIDTH, width, e.EGL_HEIGHT, height, e.EGL_NONE])
            ctx = e.eglCreateContext(display, configs[0], e.EGL_NO_CONTEXT, None)
            e.eglMakeCurrent(display, surface, surface, ctx)
            try:
                yield
            finally:
                e.eglMakeCurrent(display, e.EGL_NO_SURFACE, e.EGL_NO_SURFACE, e.EGL_NO_CONTEXT)
                e.eglDestroyContext(display, ctx)
                e.eglDestroySurface(display, surface)
        finally:
            e.eglTerminate(display)
    else:
        raise ValueError('set PYOPENGL_PLATFORM to osmesa or egl')


def main():
    w, h, n = 640, 480, 4096
    rng = np.random.default_rng(20261118)
    centres = rng.uniform(-1, 1, (n, 1, 3))
    offsets = [[0., 0., 0.], [.06, 0., 0.], [0., .08, 0.]]
    vertices = (centres + offsets).astype(np.float32).reshape(-1, 3)
    colours = np.repeat(rng.integers(0, 256, size=(n, 3), dtype=np.uint8), 3, axis=0)
    with context(w, h):
        GL.glViewport(0, 0, w, h)
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glEnableClientState(GL.GL_VERTEX_ARRAY)
        GL.glEnableClientState(GL.GL_COLOR_ARRAY)
        GL.glVertexPointer(3, GL.GL_FLOAT, 0, vertices)
        GL.glColorPointer(3, GL.GL_UNSIGNED_BYTE, 0, colours)
        samples, hashes = [], set()
        for i in range(36):
            start = perf_counter()
            GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
            GL.glDrawArrays(GL.GL_TRIANGLES, 0, len(vertices))
            raw = GL.glReadPixels(0, 0, w, h, GL.GL_RGB, GL.GL_UNSIGNED_BYTE)
            if i >= 5:
                samples.append(1000 * (perf_counter() - start))
                hashes.add(hashlib.sha256(raw).hexdigest())
        if len(hashes) != 1 or not any(raw):
            raise ValueError('non-repeatable or empty RGB readback')
        print(json.dumps({'platform': os.environ['PYOPENGL_PLATFORM'], 'threads': os.getenv('LP_NUM_THREADS'),
                          'renderer': GL.glGetString(GL.GL_RENDERER).decode(), 'version': GL.glGetString(GL.GL_VERSION).decode(),
                          'rgb_sha256': hashes.pop(), 'median_ms': round(median(samples), 3), 'frames': len(samples)}))


if __name__ == '__main__':
    main()
