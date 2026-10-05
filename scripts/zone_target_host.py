"""Native T13 host adapter. All physics/event truth stays on this side."""
import base64

from harness.zone_own_team_host import OwnCamTeamHost
from harness.zone_target_executor import TargetOwnExecutor
from scripts.run_zone_study_integration import StudyTeamHost


class _TargetHost(OwnCamTeamHost):
    def _capture(self, rid, now):
        # Periodic, explicit and macro-completion requests can coincide. One
        # physical instant supplies at most one identity observation per robot.
        # Keep stale/reordered *frames* fail-closed in IdentityJobs; only merge
        # equal-time host requests, never a backwards clock or another robot.
        captured = self.__dict__.setdefault('_target_capture_times', {})
        if rid in captured and now == captured[rid]:
            return None
        result = super()._capture(rid, now)
        if not self.robots[rid].dead:
            captured[rid] = now
        return result

    def __init__(self, spec, student, *, root, study_layer, frames_dir=None, scene=None, pose_factory=None):
        from sim.zone_target_scene import TargetScene
        from sim.zone_cargo_contact import base_profile
        if scene is not None:
            raise ValueError('T13 requires its registered standard Scene')
        scene = TargetScene.from_spec(spec, base_profile(spec['contact_profile']))
        from sim.render_profile import install
        install(scene, spec['render_profile'])
        super().__init__(spec, student, root=root, study_layer=study_layer, frames_dir=frames_dir,
                         scene=scene, pose_factory=pose_factory)
        self.target_inputs = frames_dir.parent/'target_inputs'
        for rid, slot in self.robots.items():
            # The closure receives no capability for reading the host/world.
            def cancel(now, reason, _rid=rid):
                self._drop_scheduled(_rid, now, reason)
            slot.executor = TargetOwnExecutor(slot.executor, visual_catalogue=spec['visual_catalogue'],
                                              cancel_scheduled=cancel)

    def _capture_raw(self, rid, now):
        super()._capture_raw(rid, now)
        r = self.robots[rid].executor.recognizer
        directory = self.target_inputs/rid
        directory.mkdir(parents=True, exist_ok=True)
        for did, row in r.candidates.items():
            (directory/(did+'.png')).write_bytes(base64.b64decode(row['attention_b64']))


class TargetStudyHost(StudyTeamHost, _TargetHost):
    """Reuse native stepping, provider lifecycle and original hidden events."""

    def __init__(self, spec, student, **kwargs):
        # Direct construction must not bypass the runner's v3 admission or
        # reach a v2 Scene/worker with a newly selected v3 map.
        from harness.zone_final_environment import registry
        if spec['map'] in registry()['maps'] or spec.get('robot_model') == 'masterpi_v3':
            raise ValueError('FINAL_V3_TARGET_HOST_AND_CONSUMERS_REQUIRED')
        super().__init__(spec, student, **kwargs)

    def _physics_until(self, t_end):
        # Call the event injector at each actual physics tick, including setup
        # settling. Actors never receive these event times or effects.
        if not hasattr(self, 'hidden_physics'):
            return super()._physics_until(t_end)
        dt = float(self.world.model.opt.timestep)
        while float(self.world.data.time) < t_end-1e-9:
            self.hidden_tick(float(self.world.data.time))
            super()._physics_until(min(t_end, float(self.world.data.time)+dt))
