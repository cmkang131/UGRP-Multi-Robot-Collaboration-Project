"""Grounding glue that lets the UNCHANGED VisibleOnlyGraspTeacher pick a can.

DERIVED / UNVERIFIED (solo-e2e/20261024): never exercised by a physics run.

The grasp teacher (sim/grasp_act_teacher_v3.py) is written around a beam end:
it reads ``world['beam']['ends'][end]`` / ``['pose'][2]`` and the
``visible_probes`` of the end's colour band. This module does not touch that
code. ``SoloVisibleWorld`` post-processes the visible-world model so the same
fields describe a can:

* band measurements (the parked distractor beam's bands) are dropped, so the
  beam never drives the teacher;
* the can's own visible-cargo measurement (same visibility rule as any cargo:
  at least a third of its probes visible) becomes the pseudo ``beam``:
  ``ends[*]`` = the can centre at the catalogue grasp height, ``pose[2]`` = the
  bearing from the robot to the can at FIRST sight, latched (a can has no
  heading; a latched bearing keeps the approach line fixed instead of
  chasing the robot's own motion);
* ``visible_probes`` = max(5, visible_n) on ticks where the can is currently
  seen, else 0 (the teacher's ``>= 5`` gate);
* the can is removed from ``objects`` and from the visibility ``objects``
  list so the teacher does not plan around its own target.

Inputs are the visible measurements and the robot's own issued-command
odometry only (what ``VisibleWorld`` already uses). The known grasp height is
fixed catalogue geometry, the same status as the beam's "known rigid shape".

``SnapshotCargo`` lets ``scripts/run_grasp_act_teacher.snapshot`` (eval-only
truth) accept the can: that function indexes ``part.size[2]`` for every
collision part, which a cylinder does not have, so the can's collision shell
is described by its bounding box instead.
"""
from __future__ import annotations

import math
from types import SimpleNamespace

from harness.grasp_act_visible_world import VisibleWorld
from sim.zone_cargo import GRASP_Z_M, CargoInstance, kind


class SoloVisibleWorld(VisibleWorld):
    def __init__(self, rid, end, cargo_id, **kwargs):
        super().__init__(rid, end, **kwargs)
        self.cargo_id = cargo_id
        self.latched_yaw = None

    def observe(self, measurements, now, *, comparison_pose=None):
        kept = [m for m in measurements if m['kind'] != 'band']
        world = super().observe(kept, now, comparison_pose=comparison_pose)
        seen_now = next((m for m in kept if m['id'] == self.cargo_id), None)
        entry = self.memory.get(self.cargo_id)
        beam = None
        if entry is not None and entry['kind'] == 'cargo':
            x, y = entry['xyz'][:2]
            if self.latched_yaw is None:
                self.latched_yaw = math.atan2(y - self.pose[1], x - self.pose[0])
            centre = [x, y, GRASP_Z_M]
            beam = {'pose': [x, y, self.latched_yaw], 'ends': {'teal': list(centre), 'blue': list(centre)},
                    'source': 'visible cargo + latched first-sight bearing + catalogue grasp height',
                    'seen_t': entry['seen_t']}
        world['beam'] = beam
        world['objects'] = {k: v for k, v in world['objects'].items() if k != self.cargo_id}
        vis = world['visibility'][self.rid]
        vis['objects'] = [k for k in vis['objects'] if k != self.cargo_id]
        vis['visible_probes'] = max(5, seen_now['visible_n']) if seen_now is not None else 0
        return world


class SnapshotCargo:
    """Stand-in for a CargoInstance in ``snapshot()`` (collision shell as a bounding box)."""

    def __init__(self, inst: CargoInstance):
        spec = inst.spec()
        self.inst = inst
        self.item_id, self.kind, self.body = inst.item_id, inst.kind, inst.body
        parts = []
        for p in spec.parts:
            if not p.collision:
                continue
            size = tuple(p.size)
            if p.shape == 'cylinder':
                size = (size[0], size[0], size[1])
            parts.append(SimpleNamespace(name=p.name, collision=True, size=size))
        self._spec = SimpleNamespace(parts=parts, landing_half_extents_m=spec.landing_half_extents_m)

    def spec(self):
        return self._spec

    def geom(self, part):
        return self.inst.geom(part)


def cargo_instance(plan_cargo):
    """CargoInstance from the plan's solo_cargo entry (setup-only pose)."""
    kind(plan_cargo['kind'])
    return CargoInstance(plan_cargo['item_id'], plan_cargo['kind'], tuple(float(v) for v in plan_cargo['pose']))


def add_solo_cargo(scene, plan_cargo):
    """Append the plan's small cargo to a not-yet-built scene (call before build_world).

    The scene's own transform adds the cargo XML and ``setup`` places it at the
    plan pose; the parked pair beam stays in the scene as an inert distractor.
    """
    inst = cargo_instance(plan_cargo)
    if any(c.item_id == inst.item_id for c in scene.cargo):
        raise ValueError('solo cargo id already in the scene')
    scene.cargo = list(scene.cargo) + [inst]
    record = {'item_id': inst.item_id, 'kind': inst.kind, 'pose': list(inst.pose)}
    scene.config['cargo_set'] = {**scene.config.get('cargo_set', {}),
                                 'items': [*scene.config.get('cargo_set', {}).get('items', []), record]}
    return inst
