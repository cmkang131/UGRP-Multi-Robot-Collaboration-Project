"""Count the actual payload crossing the diagnostic's controller boundary.

This audits delivered inputs, not all simulator reads: the backend/evaluator must
read world state to simulate and score. No backend/evaluator object is delivered.
Rejected inputs are counted separately and never counted as accepted reads.
"""
import copy


class InputAudit:
    COMMANDS = {'initial_servo_command': {'pulses'}, 'arm': {'servo_id', 'pulse'},
                'look': {'pan_pulse'}, 'mecanum': {'forward', 'left', 'turn', 'duration_s'},
                'drive': {'forward', 'turn', 'duration_s'}, 'hold': set(), 'stop': set()}

    def __init__(self, robot_id):
        self.robot_id = robot_id
        self.counts = dict(own_rgb_frames=0, issued_command_records=0,
            top_rgb_frames=0, peer_rgb_frames=0, truth_pose_inputs=0,
            invisible_measurements=0, held_world_reads=0, rejected_inputs=0)

    def receive(self, controller, *, camera, payload):
        if (camera != 'robot_cam' or payload.get('robot_id') != self.robot_id or
                set(payload) != {'robot_id', 't', 'frame_id', 'rgb', 'sha256'}):
            self.counts['rejected_inputs'] += 1
            raise ValueError('OWN_ROBOT_CAMERA_REQUIRED' if camera != 'robot_cam' else 'INPUT_AUDIT_ALLOWLIST')
        self.counts['own_rgb_frames'] += 1
        return controller.receive(**payload)

    def command(self, controller, row):
        fields = self.COMMANDS.get(row.get('kind'))
        if fields is None or set(row) != fields | {'t', 'kind'}:
            self.counts['rejected_inputs'] += 1
            raise ValueError('INPUT_AUDIT_COMMAND_ALLOWLIST')
        # Nested initial state is exclusively numeric issued servo pulses.
        if row['kind'] == 'initial_servo_command' and any(
                str(k) not in {'1', '2', '3', '4', '5', '6'} or type(v) not in (int, float)
                for k, v in row['pulses'].items()):
            self.counts['rejected_inputs'] += 1
            raise ValueError('INPUT_AUDIT_SERVO_ALLOWLIST')
        self.counts['issued_command_records'] += 1
        return controller.command(copy.deepcopy(row))

    def static_map(self, payload, sha256):
        allowed = {'map_id', 'version', 'frame', 'bounds_m', 'obstacles', 'regions', 'passages'}
        if (set(payload) != allowed or len(sha256) != 64 or
                any(c not in '0123456789abcdef' for c in sha256)):
            self.counts['rejected_inputs'] += 1
            raise ValueError('INPUT_AUDIT_STATIC_GEOMETRY_ALLOWLIST')
        self.counts['authored_static_map_inputs'] = self.counts.get('authored_static_map_inputs', 0)+1
        return copy.deepcopy(payload)

    def snapshot(self):
        return dict(schema='ugrp.selfmap_input_audit.v1', measured=True,
            scope='all delivered controller payloads at writer boundary; excludes evaluation/plant reads',
            **self.counts)
