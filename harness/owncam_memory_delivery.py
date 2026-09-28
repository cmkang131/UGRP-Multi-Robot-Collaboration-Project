"""Active provider-injectable memory adapter; recorded memory-v2 stays frozen."""
from harness.m1_owncam_memory import M1OwnCamDeliveryMem as FrozenMemoryDelivery
from harness.owncam_delivery_shared import SharedPoseDelivery, SharedLegDriver
from harness.owncam_drive_mem import MemoryLookPolicy
from harness.owncam_drive import CARRY_POSTURE
from harness.owncam_memory import OwnCamMemory


class SharedMemoryLeg(MemoryLookPolicy, SharedLegDriver):
    def __init__(self, memory, shared_loc, *args, **kwargs):
        super().__init__(shared_loc, *args, **kwargs)
        self._init_memory_policy(memory)


class M1OwnCamDeliveryMem(FrozenMemoryDelivery, SharedPoseDelivery):
    def __init__(self, static_map, params, *, pose_source=None, landmark_provider=None,
                 memory_factory=OwnCamMemory, **kwargs):
        from harness.owncam_memory_inputs import memory_inputs
        pose_source, landmark_provider, self._provider_inputs = memory_inputs(
            static_map, params, kwargs.get('seed', 0), pose_source, landmark_provider)
        SharedPoseDelivery.__init__(self, static_map, params, pose_source=pose_source, **kwargs)
        self.memory = memory_factory(static_map, params, robot_id=self.robot_id,
                                      provider=landmark_provider, on_event=self._memory_event)
        self.target_track_id: str | None = None
        self.closer_done_tracks: list[str] = []
        self.skipped_viewpoints: list[tuple[float, float]] = []
        self.revisit = False
        self.reverify_done = False
        self.slot_checked = False
        self.slot_record: dict | None = None
        self.gate_modes: list[dict] = []
        self.abandoned = 0
        self._held = False

    def on_frame(self, now, obs, rgb):
        report = SharedPoseDelivery.on_frame(self, now, obs, rgb)
        servo = {int(k): int(v) for k, v in obs['actuator_state']['servo_pulses'].items()}
        loaded = report.load_state == 'loaded'
        out = self.memory.observe_frame(now, frame_id=int(obs['frame_id']), image=obs['image'], servo=servo,
                                        report=report, arm_settled_s=now - self.pose.loc.last_servo_cmd_t,
                                        loaded=loaded, provider_inputs=self._provider_inputs())
        if loaded and not self._held:
            self.memory.mark_held(now)
        elif self._held and not loaded:
            self.memory.mark_released(now)
        self._held = loaded
        for row in out.get('boxes', []):
            if row['kind'] == self.box_kind:
                self.cyan.append({'t': round(now, 3), **row})
        return report

    def _start_leg(self, goal, *, loaded):
        self.leg = SharedMemoryLeg(self.memory, self.pose.loc, self.map, self.params, loaded=loaded, goal_xy=goal,
                                 door_xy=self.door_xy, keepouts=self._keepouts(), initial_servo=dict(self.servo),
                                 seed=self.seed)
        if loaded:
            self.leg.drive_pose = dict(CARRY_POSTURE)
        self.leg_goal = tuple(goal)

    def summary(self):
        out = super().summary()
        from harness.owncam_memory_inputs import result_label
        out['landmark_provider']['result_label'] = result_label(self.memory.provider)
        return out
