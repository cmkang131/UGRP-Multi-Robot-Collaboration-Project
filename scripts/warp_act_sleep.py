"""Pinned upstream sleep implementation with world-indexed dof lengths.

All original values are preserved. The sole numerical change is an array index;
no sleeping predicate, tolerance, physics or installed package file is edited.
"""
import hashlib
import importlib.util
import sys
from pathlib import Path

PINNED_SLEEP_SHA256 = '5b50688a8949afa30df1ae6ce2195132fdf50cf6ed821746badd8e06b92d91b0'


def install(nv, out):
    from mujoco_warp._src import sleep, forward
    raw = Path(sleep.__file__).read_bytes()
    if hashlib.sha256(raw).hexdigest() != PINNED_SLEEP_SHA256:
        raise RuntimeError('world-batched sleep adapter requires exact pinned upstream source')
    before = 'weight = dof_length[dof_idx]'
    after = f'weight = dof_length[worldid * {int(nv)} + dof_idx]'
    text = raw.decode()
    if text.count(before) != 1:
        raise RuntimeError('unexpected upstream dof_length read sites')
    generated = Path(out)/'upstream_sleep_world_v1.py'
    generated.write_text(text.replace(before,after))
    spec = importlib.util.spec_from_file_location('ugrp_sleep_world_v1',generated)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    forward.sleep = module
    return dict(upstream_sha256=PINNED_SLEEP_SHA256,generated_sha256=hashlib.sha256(generated.read_bytes()).hexdigest(),
        before=before,after=after,scope='one world-specific exact array lookup; all sleep/wake predicates unchanged')
