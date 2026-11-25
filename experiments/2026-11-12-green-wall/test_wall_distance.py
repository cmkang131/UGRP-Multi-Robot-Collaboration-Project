import unittest
import numpy as np
from wall_distance import distance_from_contact,infer_wall_actions,design_scale


class DistanceTests(unittest.TestCase):
    def test_metric_gap_from_geometry_not_motor_time(self):
        p=np.c_[np.full(81,2.),np.linspace(-1,1,81)]
        a=distance_from_contact(p,[0,0],10.)
        b=distance_from_contact(p,[.5,0],10.)
        c=distance_from_contact(p,[0,.5],10.)
        self.assertAlmostEqual(a['wall_gap_cm'],20.)
        self.assertAlmostEqual(b['wall_gap_cm'],15.)
        self.assertAlmostEqual(c['wall_gap_cm'],20.)
        p=np.r_[p,[[30,0],[-20,.3],[19,-.2]]]
        self.assertAlmostEqual(distance_from_contact(p,[.5,0],10.)['wall_gap_cm'],15.)

    def test_direction_uses_observed_gap_and_rejects_sideways(self):
        before=dict(wall_gap_cm=20.,line_rms_cm=.02,camera_xy_cm=[0,0])
        after=dict(wall_gap_cm=23.,line_rms_cm=.02,camera_xy_cm=[-3,0])
        self.assertEqual(infer_wall_actions(before,after)['away'],'left')
        self.assertEqual(infer_wall_actions(after,before)['toward'],'left')
        sideways=dict(wall_gap_cm=20.1,line_rms_cm=.02,camera_xy_cm=[0,3])
        with self.assertRaisesRegex(ValueError,'unresolved|tangential'):infer_wall_actions(before,sideways)

    def test_scale_is_explicit_design_estimate(self):
        scale=design_scale()
        self.assertGreater(scale['camera_height_cm'],0)
        self.assertFalse(scale['independently_measured'])
        self.assertIn('PWM',scale['source'])


if __name__=='__main__':unittest.main()
