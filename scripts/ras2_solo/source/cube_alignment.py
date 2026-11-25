"""Physical cube face selection layered on the published alignment controller."""


def cube_aligner_type(published_type):
    class CubeFaceAligner(published_type):
        def step(self, jpeg, now):
            command = super().step(jpeg, now)
            row = self.trace[-1]
            # The published controller reaches face_check only after its valid,
            # stable contour, bearing, yaw and distance conditions all pass.
            # A cube has equivalent faces: the 39 mm wide-face discriminator
            # of the 34x40 mm training object must not trigger an extra orbit.
            # No pixel, projection, quality threshold or range is fabricated.
            if 'face_check' in row:
                self.force = 0
                self.force_prev = None
                self.quarter_used = False
                self.face = 'cube_equivalent'
                self.done, self.reason = True, 'aligned_cube_equivalent_face'
                if self.pulses and self.pulses[-1]['tick'] == row['tick']:
                    self.pulses.pop()
                command = self.contract.command(dict(command, wheels=[0.]*4, duration_s=[0.]*4))
                row.update(command=command, pulse=None,
                           object_shape='cube', equivalent_faces=True)
            return command
    return CubeFaceAligner


def configure_cube(approach):
    from types import SimpleNamespace
    approach.align_mod = SimpleNamespace(FaceAligner=cube_aligner_type(approach.align_mod.FaceAligner))


def self_test():
    from unittest.mock import patch
    from run import SurveyApproach, contract
    import math
    approach = SurveyApproach(contract, lambda entries: 0)
    module = approach.align_mod
    entry = {'kind': 'red', 'x': .3, 'y': 0., 'distance_m': .3,
             'bearing_rad': 0., 'observations': 2, 'dispersion': 0.}
    posture = {1: 2000, 3: 500, 4: 2500, 5: 1320, 6: 1500}
    base = {'valid': True, 'yaw_rad': 0., 'cx': 286.9, 'cy': 327.,
            'contact_x_m': .203, 'contact_y_m': 0., 'area': 12000,
            'long_edge_m': .03}
    wrapped = cube_aligner_type(module.FaceAligner)
    for name, estimate, expected in (
            ('cube_at_valid_station', base, 'aligned_cube_equivalent_face'),
            ('too_far', dict(base, contact_x_m=.26), None),
            ('off_center', dict(base, cx=380.), None),
            ('wrong_yaw', dict(base, yaw_rad=math.radians(12)), None),
            ('missing_box', {'valid': False, 'hint': None, 'reject': 'missing'}, None)):
        actor = wrapped(approach.baseline, contract, [entry], 0, posture)
        with patch.object(module, 'estimate', return_value=estimate):
            for i in range(6):
                command = actor.step(b'fixture', i*.1)
        assert actor.reason == expected, (name, actor.reason)
        if expected:
            assert actor.done and not actor.quarter_used
            assert command['wheels'] == [0.]*4 and not actor.pulses
        else:
            assert not actor.done
    original = module.FaceAligner(approach.baseline, contract, [entry], 0, posture)
    with patch.object(module, 'estimate', return_value=base):
        for i in range(6):
            original.step(b'fixture', i*.1)
    assert original.quarter_used and not original.done
    return {'cube_face_cases': 5, 'published_rectangle_behavior_unchanged': True,
            'physical_commands_sent': 0}


if __name__ == '__main__':
    import json
    print(json.dumps(self_test(), indent=2))
