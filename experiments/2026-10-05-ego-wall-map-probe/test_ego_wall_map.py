"""Stage C recorder: chassis-frame records, settle gate, header, off state. Synthetic, standalone. Refs #216."""
from __future__ import annotations

import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent / 'code'))
import ego_wall_map as ewm  # noqa: E402

SERVO = {1: 2000, 3: 740, 4: 2320, 5: 1320, 6: 1500}
SEG = {'range_first_m': 1.0, 'bearing_first_rad': 0.0, 'range_last_m': 1.0, 'bearing_last_rad': math.pi/2, 'height_m': 0.4}


class RecorderTests(unittest.TestCase):
    def test_arm_axis_offset_is_the_modelled_mount(self):
        self.assertAlmostEqual(ewm.ARM_AXIS_OFFSET_M, 0.0482)

    def test_end_points_are_moved_from_the_arm_axis_frame_to_the_chassis_origin(self):
        # camera nadir 0.10 m ahead of the arm axis; face end points 1 m ahead and 1 m to the left of the nadir
        r1, t1, r2, t2, h = ewm.segment_to_chassis(SEG, (0.10, 0.0))
        self.assertAlmostEqual(r1, 0.10 + 1.0 + 0.0482, places=4)
        self.assertAlmostEqual(t1, 0.0, places=4)
        x2, y2 = 0.10 + 0.0482, 1.0
        self.assertAlmostEqual(r2, math.hypot(x2, y2), places=3)
        self.assertAlmostEqual(t2, math.atan2(y2, x2), places=3)
        self.assertEqual(h, 0.4)
        self.assertIsNone(ewm.segment_to_chassis({**SEG, 'height_m': None}, (0., 0.))[4])
        self.assertAlmostEqual(ewm.segment_to_chassis(SEG, (0., 0.), arm_axis_offset_m=0.)[0], 1.0, places=4)

    def test_the_arm_axis_offset_is_recorded_only_by_default_and_applied_on_request(self):
        self.assertEqual(ewm.DEFAULT_APPLIED_OFFSET_M, 0.0)
        results = {}
        for label, kwargs in (('default', {}), ('zero', {'arm_axis_offset_m': 0.0}),
                              ('applied', {'arm_axis_offset_m': ewm.ARM_AXIS_OFFSET_M})):
            m = ewm.EgoWallMap(enabled=True, settle_s=None, **kwargs)
            m.update_command(1.0, SERVO)
            results[label] = (m.observe(1.0, SERVO, False, (0.10, 0.0), [SEG], 1), m.header())
        self.assertEqual(results['default'][0], results['zero'][0])
        self.assertEqual(results['default'][0]['seg'][0][0], 1.1)               # nadir 0.10 + range 1.0, no shift
        self.assertAlmostEqual(results['applied'][0]['seg'][0][0], 1.1 + ewm.ARM_AXIS_OFFSET_M, places=4)
        self.assertEqual(results['default'][1]['arm_axis_offset_m'], 0.0)
        self.assertEqual(results['applied'][1]['arm_axis_offset_m'], ewm.ARM_AXIS_OFFSET_M)
        for label in results:                                                     # the physical offset is always recorded
            self.assertEqual(results[label][1]['arm_axis_offset_recorded_m'], ewm.ARM_AXIS_OFFSET_M)

    def test_record_fields(self):
        m = ewm.EgoWallMap(enabled=True, settle_s=None)
        m.update_command(1.0, SERVO)
        rec = m.observe(1.0, SERVO, False, (0.1, 0.0), [SEG], 42)
        self.assertEqual(set(rec), {'t_sim', 'seg', 'posture', 'load', 'view_index'})
        self.assertEqual((rec['t_sim'], rec['posture'], rec['load'], rec['view_index']), (1.0, 'other', False, 42))
        self.assertEqual(len(rec['seg']), 1)
        self.assertEqual(len(rec['seg'][0]), 5)

    def test_high_posture_label(self):
        high = {1: 1500, 3: 896, 4: 2035, 5: 1894, 6: 1500}
        self.assertEqual(ewm.posture_label(high), 'high')
        self.assertEqual(ewm.posture_label(SERVO), 'other')

    def test_no_wall_no_record_but_the_settled_frame_is_counted(self):
        m = ewm.EgoWallMap(enabled=True, settle_s=None)
        self.assertIsNone(m.observe(1.0, SERVO, False, (0., 0.), [], 1))
        self.assertEqual((len(m.records), m.frames_seen), (0, 1))


class SettleGateTests(unittest.TestCase):
    def test_gate_per_load_class_and_reset_on_a_command_change(self):
        m = ewm.EgoWallMap(enabled=True)
        self.assertEqual(m.settle_s, {'unloaded': 0.25, 'loaded': 2.25})
        m.update_command(10.0, SERVO)
        self.assertFalse(m.settled(10.2, False))
        self.assertTrue(m.settled(10.25, False))
        self.assertFalse(m.settled(11.0, True))          # the beam makes the arm settle slower
        self.assertTrue(m.settled(12.25, True))
        m.update_command(11.0, {**SERVO, 6: 1230})       # any commanded pulse changing restarts the clock
        self.assertFalse(m.settled(11.1, False))
        self.assertTrue(m.settled(11.25, False))
        m.update_command(11.5, {**SERVO, 6: 1230})      # same command: the clock keeps running
        self.assertTrue(m.settled(11.5, False))

    def test_unsettled_frame_is_not_recorded(self):
        m = ewm.EgoWallMap(enabled=True)
        m.update_command(5.0, SERVO)
        self.assertIsNone(m.observe(5.1, SERVO, False, (0., 0.), [SEG], 1))
        self.assertEqual(len(m.records), 0)
        self.assertIsNotNone(m.observe(5.3, SERVO, False, (0., 0.), [SEG], 2))

    def test_repeated_sightings_are_all_kept(self):
        m = ewm.EgoWallMap(enabled=True, settle_s=None)
        for i in range(3):
            m.update_command(float(i), SERVO)
            m.observe(float(i), SERVO, False, (0., 0.), [SEG], i)
        self.assertEqual([r['t_sim'] for r in m.records], [0.0, 1.0, 2.0])


class OffStateTests(unittest.TestCase):
    def test_disabled_map_keeps_and_returns_nothing(self):
        m = ewm.EgoWallMap()
        self.assertFalse(m.enabled)
        m.update_command(1.0, SERVO)
        self.assertFalse(m.settled(100.0, False))
        self.assertIsNone(m.observe(100.0, SERVO, False, (0., 0.), [SEG], 1))
        self.assertEqual((m.records, m.frames_seen), ([], 0))


class FileTests(unittest.TestCase):
    def test_header_records_the_arm_axis_offset_and_the_file_round_trips(self):
        m = ewm.EgoWallMap(enabled=True, settle_s=None)
        m.update_command(1.0, SERVO)
        m.observe(1.0, SERVO, False, (0.1, 0.0), [SEG], 7)
        with tempfile.TemporaryDirectory() as d:
            m.save(Path(d)/'ego_map.jsonl')
            lines = (Path(d)/'ego_map.jsonl').read_text().splitlines()
            header, records = ewm.EgoWallMap.load(Path(d)/'ego_map.jsonl')
        self.assertEqual(len(lines), 2)
        self.assertEqual(header['arm_axis_offset_m'], 0.0)                       # recorded only: nothing applied by default
        self.assertEqual(header['arm_axis_offset_recorded_m'], ewm.ARM_AXIS_OFFSET_M)
        self.assertEqual(header['schema'], 'ego-wall-map/1')
        self.assertEqual((header['records'], header['settled_frames_seen']), (1, 1))
        self.assertEqual(records, [json.loads(json.dumps(r)) for r in m.records])


if __name__ == '__main__':
    unittest.main(verbosity=2)
