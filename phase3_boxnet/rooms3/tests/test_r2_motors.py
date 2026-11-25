"""Test the native stage bindings with scripted motor effects and no actor inference."""
import importlib.util
import json
import math
import sys
import unittest
from unittest.mock import Mock, patch

from handover import layout
from rooms3.maps import ROOT


@unittest.skipUnless(importlib.util.find_spec("mujoco"), "native controller imports require MuJoCo")
class StageBindings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT / "exec"))
        import sim
        sim.__path__.insert(0, str(ROOT / "exec-repo/sim"))
        from rooms3 import motors
        cls.motors = motors

    def setUp(self):
        self.scene = json.loads((ROOT / "rooms3/scenes/seed-3/map.json").read_bytes())
        self.w = Mock(scene=self.scene, tracked="box_seen_at_lift")
        self.backend = self.motors.NativeBackend.__new__(self.motors.NativeBackend)
        self.backend.w, self.backend.scene, self.backend.actor = self.w, self.scene, object()
        self.policy = Mock()
        self.backend.prepare = Mock(return_value=self.policy)

    def test_all_door_release_stands_are_in_the_senders_room_facing_the_directed_pad(self):
        for name, pad in self.scene["pads"].items():
            rid, dest = pad["from"], pad["to"]
            self.w.tracked = "box_seen_at_lift"
            self.policy.reset_mock()
            with patch.object(self.motors, "release_held") as release:
                self.assertEqual(self.backend.move(rid, {"id": "view-track"}, dest), "box_seen_at_lift")
            self.policy.pick.assert_called_once_with("donor")
            release.assert_called_once_with(self.policy, rid)
            _, stand, face = self.policy.drive.call_args_list[1].args
            self.assertGreater(layout.margin(self.scene["rooms"][rid]["bounds"], *stand), .1)
            self.assertEqual(stand[1], pad["xy"][1])
            self.assertAlmostEqual(stand[0] + layout.RELEASE_STAND * math.cos(face), pad["xy"][0], msg=name)
            self.policy.find_sign.assert_not_called()

    def test_sign_placement_calls_the_stock_wrist_localization_stage_before_release(self):
        def release(policy, rid):
            policy.pick.assert_called_once_with("donor")
            policy.find_sign.assert_called_once_with(rid)
        with patch.object(self.motors, "release_held", side_effect=release):
            self.backend.move("r3", {"id": "own-track"}, "target")
        self.assertIs(self.motors.MovePolicy.find_sign, self.motors.Policy.find_sign)
        self.assertIs(self.motors.MovePolicy.pick, self.motors.Policy.pick)

    def test_receiver_uses_own_scan_stand_and_selects_only_the_observed_pad_track(self):
        pad = self.scene["pads"]["r2_r1"]
        track = {"colour": "red", "pad": "r2_r1", "xy": pad["xy"]}
        self.w.record.seq = 0
        policy = self.motors.MovePolicy(self.w, None, "r1", track)
        policy.drive = Mock()
        origin = [pad["xy"][0] - layout.SCAN_STAND, pad["xy"][1], 0.]
        policy.pose = Mock(return_value=origin)
        policy.prepare_pick("r1")
        policy.drive.assert_called_once_with("r1", origin[:2], 0.)
        survey = policy.box_survey(origin, "donor")
        entries = [{"kind": "red", "x": .4, "y": .4}, {"kind": "cyan", "x": layout.SCAN_STAND, "y": 0.},
                   {"kind": "red", "x": layout.SCAN_STAND, "y": 0.}]
        self.assertEqual(survey._select(entries), 2)
        self.assertIsNone(survey._select(entries[:2]))
