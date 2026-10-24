"""Grounding glue that lets the UNCHANGED VisibleOnlyGraspTeacher pick a box.

DERIVED / UNVERIFIED (solo-e2e/20261024): never exercised by a physics run.

The cargo is the scenario's own cyan box replica (cargo v6, see
``harness/solo_carry_contract.py``): the production dispatch box, half extents
(.017, .020, .016) m, mass .030 kg, one free joint, one collision geom
``<body>_geom`` (``sim/research_dispatch_arena.py:135-137``,
``sim/warehouse_mission.py:357-363``, replicated with paint only by
``sim/zone_arena.py:418-428``). Nothing is added to the scene XML.

The grasp teacher (sim/grasp_act_teacher_v3.py) is written around a beam end:
it reads ``world['beam']['ends'][end]`` / ``['pose'][2]`` and the
``visible_probes`` of the end's colour band, and stands ``STATION_M`` behind the
end along ``pose[2]`` facing it (``sim/grasp_act_teacher_v3.py:454-456``). This
module does not touch that code. ``SoloVisibleWorld`` post-processes the
visible-world model so the same fields describe the box:

* band measurements (the parked distractor beam's bands) are dropped, so the
  beam never drives the teacher;
* the box's own visible-cargo measurement (same visibility rule as any cargo:
  at least a third of its probes visible) becomes the pseudo ``beam``:
  ``ends[*]`` = the box centre at the calibrated box grasp height
  (``sim/zone_cargo.py:34`` ``GRASP_Z_M`` = .024 m), ``pose[2]`` = the box's
  visible yaw folded by pi to the side facing the robot at FIRST sight. The
  box footprint is 180-degree symmetric (34 x 40 mm; the same-shape calibration
  block declares ``landing_yaw_symmetry_deg=180``, ``sim/zone_cargo.py:208-213``),
  so both sides give the same grasp: the jaws close across the 40 mm side
  (``sim/zone_cargo.py:38-41``). The fold parity is latched so the approach side
  never flips; the yaw itself follows the current visible estimate;
* ``visible_probes`` = max(5, visible_n) on ticks where the box is currently
  seen, else 0 (the teacher's ``>= 5`` gate);
* the box is removed from ``objects`` and from the visibility ``objects``
  list so the teacher does not plan around its own target.

Inputs are the visible measurements and the robot's own issued-command
odometry only (what ``VisibleWorld`` already uses). The known grasp height is
fixed production-box geometry, the same status as the beam's "known rigid shape".

``SoloBox`` is the snapshot / finger-force stand-in for the replica (the
runner's ``snapshot()`` and ``FormationTeacher.finger_forces`` index
``inst.body``, ``inst.geom(part)`` and ``inst.spec().parts[*].size``).
"""
from __future__ import annotations

import math
from types import SimpleNamespace

from harness import solo_carry_contract as sc
from harness.grasp_act_visible_world import VisibleWorld


def wrap(a):
    return math.atan2(math.sin(a), math.cos(a))


class SoloVisibleWorld(VisibleWorld):
    def __init__(self, rid, end, cargo_id, **kwargs):
        super().__init__(rid, end, **kwargs)
        self.cargo_id = cargo_id
        self.fold = None              # 0 or pi, latched at first sight

    def observe(self, measurements, now, *, comparison_pose=None):
        kept = [m for m in measurements if m['kind'] != 'band']
        world = super().observe(kept, now, comparison_pose=comparison_pose)
        seen_now = next((m for m in kept if m['id'] == self.cargo_id), None)
        entry = self.memory.get(self.cargo_id)
        beam = None
        if entry is not None and entry['kind'] == 'cargo':
            x, y = entry['xyz'][:2]
            yaw = float(entry['yaw'])
            if self.fold is None:
                bearing = math.atan2(y - self.pose[1], x - self.pose[0])
                self.fold = 0. if math.cos(wrap(yaw - bearing)) >= 0. else math.pi
            heading = wrap(yaw + self.fold)
            centre = [x, y, sc.GRASP_Z_M]
            beam = {'pose': [x, y, heading], 'ends': {'teal': list(centre), 'blue': list(centre)},
                    'source': 'visible box + latched near-side fold + production-box grasp height',
                    'seen_t': entry['seen_t']}
        world['beam'] = beam
        world['objects'] = {k: v for k, v in world['objects'].items() if k != self.cargo_id}
        vis = world['visibility'][self.rid]
        vis['objects'] = [k for k in vis['objects'] if k != self.cargo_id]
        vis['visible_probes'] = max(5, seen_now['visible_n']) if seen_now is not None else 0
        return world


class SoloBox:
    """The scenario's box replica as the runner's carried-cargo handle (snapshot + finger forces)."""

    PART = 'geom'                 # replica geom name = body + '_geom' (sim/zone_arena.py:423-427)

    def __init__(self, item_id, kind, body, joint, pose, half_extents):
        self.item_id, self.kind, self.body, self.joint = item_id, kind, body, joint
        self.pose = tuple(float(v) for v in pose)
        self.half_extents = tuple(float(v) for v in half_extents)
        part = SimpleNamespace(name=self.PART, collision=True, size=self.half_extents)
        self._spec = SimpleNamespace(parts=[part], landing_half_extents_m=self.half_extents[:2])

    def spec(self):
        return self._spec

    def geom(self, part):
        return f'{self.body}_{part}'


def select_solo_cargo(scene, plan_cargo):
    """The plan's box, taken from the scene's own setup objects (call before build_world).

    Fails closed unless the item exists, is the contract's kind with the production
    box half extents, and is the ONLY item of that colour in the scene (a second
    same-colour box would make the own-RGB task ambiguous). Nothing is added.
    """
    objects = scene.config['setup_only'].get('objects') or {}
    item = objects.get(plan_cargo['item_id'])
    if item is None:
        raise ValueError(f"solo cargo {plan_cargo['item_id']!r} is not a scenario box in this scene")
    if item['kind'] != plan_cargo['kind'] or item['kind'] != sc.OBJECT_KIND:
        raise ValueError('solo cargo kind mismatch')
    if tuple(float(v) for v in item['half_extents_m']) != sc.CARGO_HALF_EXTENTS_M:
        raise ValueError('solo cargo is not the production box shape')
    same = [k for k, o in objects.items() if o['kind'] == sc.OBJECT_KIND]
    same += [c.item_id for c in getattr(scene, 'cargo', ()) if getattr(c, 'kind', None) == sc.OBJECT_KIND]
    if same != [plan_cargo['item_id']]:
        raise ValueError(f'solo cargo colour {sc.OBJECT_KIND!r} must be unique in the scene, found {same}')
    x, y, yaw = (float(v) for v in plan_cargo['pose'])
    return SoloBox(plan_cargo['item_id'], item['kind'], item['body_name'], item['joint_name'], (x, y, yaw),
                   item['half_extents_m'])


def place_solo_cargo(world, box):
    """Setup-only placement of the box at the plan pose, after ``scene.setup`` (same step as the beam).

    The body origin is the box centre: z = half height, as in the scene's own reset
    (``sim/session_scenes.py:212-220`` with ``position_m`` z = BOX_HALF[2],
    ``sim/zone_scenario_scene.py:96-100``).
    """
    import mujoco
    jid = mujoco.mj_name2id(world.model, mujoco.mjtObj.mjOBJ_JOINT, box.joint)
    if jid < 0:
        raise ValueError(f'missing cargo joint: {box.joint}')
    q, v = int(world.model.jnt_qposadr[jid]), int(world.model.jnt_dofadr[jid])
    x, y, yaw = box.pose
    world.data.qpos[q:q+7] = [x, y, box.half_extents[2], math.cos(yaw/2), 0, 0, math.sin(yaw/2)]
    world.data.qvel[v:v+6] = 0
    mujoco.mj_forward(world.model, world.data)
