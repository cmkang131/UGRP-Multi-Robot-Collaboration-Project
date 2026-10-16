"""Physics-owner half of the opt-in front-ultrasonic input (``harness.ultrasonic_input``).

``OwnUltrasonicRig`` builds one ``sim.ultrasonic_range.MujocoUltrasonic`` per
robot on the run's MuJoCo world and, every sensor period of SIM time, feeds that
robot's OWN reading to its own ``OwnRangeInput`` provider. It is a read-only
observer of the physics:

* it never calls ``mj_step`` or ``mj_forward``; it reads the world state left by
  the last completed step (the pose is the kinematics of that step, at most one
  physics timestep old). Contacts, weights and collisions are untouched, and the
  sensor is independent of any render profile (it uses ray casts on collision
  geometry groups, not the camera);
* noise comes from ``harness.ultrasonic_model.sensor_seed(episode_seed, robot)``
  with tick-indexed streams, so it never touches a global RNG and every
  condition draws the same noise at the same SIM time;
* peers are passed to the sensor only when the spec turns crosstalk on (``on_v1``
  keeps it off), so a robot's reading depends on other robots only through
  what the rays physically hit;
* only ``measure`` (the ``RangeReading``) is called. The evaluation diagnostic
  (``measure_diagnostic``: what was hit, cause) is never used here.
"""
from __future__ import annotations

import mujoco

from harness.ultrasonic_input import OwnRangeInput
from harness.ultrasonic_model import sensor_seed
from sim.ultrasonic_range import MujocoUltrasonic

V3_SONAR_SITE = 'v3_ultrasonic_site'


def sensor_site(model: mujoco.MjModel, rid: str) -> str | None:
    """MasterPi v3 robots expose a chassis-fixed sensor site; v2 uses the spec's chassis mount."""
    for name in (f'{rid}__{V3_SONAR_SITE}', V3_SONAR_SITE):
        if mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, name) >= 0:
            return name
    return None


class OwnUltrasonicRig:
    def __init__(self, model: mujoco.MjModel, data: mujoco.MjData, robots, *, episode_seed: int, range_input: OwnRangeInput):
        self.model, self.data, self.input = model, data, range_input
        self.robots = tuple(robots)
        self.seeds = {rid: sensor_seed(episode_seed, rid) for rid in self.robots}
        self.sensors = {rid: MujocoUltrasonic(model, data, rid, seed=self.seeds[rid], spec=range_input.spec,
                                              site=sensor_site(model, rid)) for rid in self.robots}
        self.last_t: float | None = None

    def tick(self, now: float) -> int:
        """Take the readings that are due at SIM time ``now`` (each robot on its own 60 ms clock)."""
        taken = 0
        for rid in self.robots:
            sensor = self.sensors[rid]
            if not sensor.due(now):
                continue
            peers = [self.sensors[q] for q in self.robots if q != rid] if sensor.spec.crosstalk else ()
            self.input.feed(rid, sensor.measure(float(now), peers=peers))
            taken += 1
        if taken:
            self.last_t = float(now)
        return taken

    def provider(self, rid: str):
        return self.input.provider(rid)

    def close(self) -> None:
        self.input.close()

    def record(self) -> dict:
        return {'sites': {rid: s.site for rid, s in self.sensors.items()},
                'noise_seeds': {rid: str(seed) for rid, seed in self.seeds.items()},
                'history_rows': self.input.rows()}
