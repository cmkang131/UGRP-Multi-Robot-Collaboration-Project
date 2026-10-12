"""Command-only sag model: pinned against the measured elevation errors of the recorded poses. Standalone. Refs #216.

The measured values are (rendered camera elevation minus FK of the commanded pulses, degrees) on settled frames of the
recorded v98 episodes (``fit_sag.py``; the model is within 0.25 deg of each pose even when that pose is left out of the fit).
The option itself (``wall_probe.detector_bias(..., sag=True)``) is off by default and off is the constant seed bias.
"""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent / 'code'))
import wall_probe as wp  # noqa: E402  (puts the markerless probe on the path)
import markerless_probe as mp  # noqa: E402
import sag_comp  # noqa: E402

# (s3, s4, s5) -> measured elevation error, deg. Unloaded: gripper open (servo 1 = 2000); loaded: gripper closed (1500).
MEASURED = {
    (508, 2432, 1320): (-0.72, False), (740, 2320, 1320): (-0.95, False), (770, 1982, 1876): (-1.44, False),
    (807, 1897, 2187): (-1.52, False), (1072, 2400, 1482): (-1.29, False), (1269, 2052, 2494): (-1.47, False),
    (891, 2036, 2054): (-6.03, True), (981, 2152, 1917): (-6.66, True), (896, 2035, 1894): (-6.54, True),
}


def servo(pose, loaded):
    return {1: 1500 if loaded else 2000, 3: pose[0], 4: pose[1], 5: pose[2], 6: 1500}


class SagModelTests(unittest.TestCase):
    def test_within_a_quarter_degree_of_every_measured_pose(self):
        for pose, (meas, loaded) in MEASURED.items():
            got = sag_comp.elevation_error_deg(servo(pose, loaded), loaded)
            self.assertAlmostEqual(got, meas, delta=0.25, msg=f'{pose} loaded={loaded}')

    def test_better_than_the_constant_bias_where_the_constant_is_wrong(self):
        for pose, (meas, loaded) in MEASURED.items():
            const = math.degrees(wp.SEED_BIAS['loaded' if loaded else 'unloaded'])
            got = sag_comp.elevation_error_deg(servo(pose, loaded), loaded)
            if abs(meas - const) > 0.4:
                self.assertLess(abs(got - meas), abs(const - meas), msg=str(pose))

    def test_the_carried_object_sags_the_camera_further_down(self):
        s = servo((896, 2035, 1894), True)
        self.assertLess(sag_comp.elevation_error_deg(s, True), sag_comp.elevation_error_deg(s, False) - 3.0)

    def test_bias_rad_is_radians(self):
        s = servo((740, 2320, 1320), False)
        self.assertAlmostEqual(sag_comp.bias_rad(s, False), math.radians(sag_comp.elevation_error_deg(s, False)))


class OptionTests(unittest.TestCase):
    def test_off_is_the_constant_seed_bias_for_both_load_states(self):
        s = servo((740, 2320, 1320), False)
        for loaded in (False, True):
            self.assertEqual(wp.detector_bias(s, loaded), mp.elevation_bias(wp.SEED_BIAS['loaded' if loaded else 'unloaded'], s))
            self.assertEqual(wp.detector_bias(s, loaded, sag=False), wp.SEED_BIAS['loaded' if loaded else 'unloaded'])

    def test_on_ignores_the_load_rule_and_uses_the_gripper_command(self):
        open_pose = servo((1072, 2400, 1482), False)            # arm pose with servo 3 >= 900, gripper open
        self.assertEqual(wp.detector_bias(open_pose, True, sag=True), wp.detector_bias(open_pose, False, sag=True))
        self.assertAlmostEqual(math.degrees(wp.detector_bias(open_pose, True, sag=True)), -1.29, delta=0.25)


if __name__ == '__main__':
    unittest.main(verbosity=2)
