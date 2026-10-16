import io
import subprocess
import unittest
from unittest.mock import patch

from scripts.real_robot_link import LinkError, RealRobotLink


PIN = "a" * 64
ARM = {"kind": "arm", "servo_id": 1, "pulse": 1800}
SAFE = {"robot_id": "r1", "servo_id": 1, "pulse_min": 1500,
        "pulse_max": 1800, "battery_min_mv": 7000, "battery_max_mv": 8400,
        "operator_ready": True}


class Response(io.BytesIO):
    status = 200


class LinkTests(unittest.TestCase):
    def setUp(self):
        self.calls = []

        def runner(args, **kwargs):
            self.calls.append(args)
            if args[-1].startswith("sha256sum"):
                return subprocess.CompletedProcess(args, 0, PIN + "  control.py", "")
            if args[-1].endswith(" probe"):
                return subprocess.CompletedProcess(args, 0, '{"ok":true,"battery_mv":7600}', "")
            return subprocess.CompletedProcess(args, 0, "DRY-RUN", "")

        self.link = RealRobotLink(host="192.168.137.218", user="ugrp1", identity="key",
            known_hosts="known", camera_url="http://127.0.0.1:18080/snapshot",
            control_sha256=PIN, run=runner,
            http=lambda *a, **k: Response(b"\xff\xd8jpeg\xff\xd9"))

    def test_default_arm_is_remote_dry_run(self):
        result = self.link.apply_arm(ARM, duration_s=.5)
        self.assertTrue(result["dry_run"])
        self.assertIn("--dry-run servo 1 1800", self.calls[-1][-1])
        self.assertFalse(result["motion_confirmed"])

    def test_sim_drive_is_rejected_before_network(self):
        with self.assertRaises(ValueError):
            self.link.apply_arm({"kind": "drive", "forward": .1}, duration_s=.5)
        self.assertEqual(self.calls, [])

    def test_live_requires_explicit_safety_profile(self):
        with self.assertRaises(LinkError):
            self.link.apply_arm(ARM, duration_s=.5, execute=True)
        self.assertFalse(any(" servo " in c[-1] for c in self.calls))

    def test_invalid_telemetry_blocks_live_command(self):
        original = self.link.run

        def run(args, **kwargs):
            if args[-1].endswith(" probe"):
                self.calls.append(args)
                return subprocess.CompletedProcess(args, 1, "", "invalid voltage")
            return original(args, **kwargs)

        self.link.run = run
        with self.assertRaises(LinkError):
            self.link.apply_arm(ARM, duration_s=.5, execute=True, safety=SAFE)
        self.assertFalse(any(" servo " in c[-1] for c in self.calls))

    def test_hardware_voltage_limits_are_enforced(self):
        safe = dict(SAFE, battery_min_mv=7800)
        with self.assertRaises(LinkError):
            self.link.apply_arm(ARM, duration_s=.5, execute=True, safety=safe)
        self.assertFalse(any(" servo " in c[-1] for c in self.calls))

    def test_mechanical_limits_are_enforced(self):
        with self.assertRaises(LinkError):
            self.link.apply_arm(dict(ARM, pulse=1850), duration_s=.5,
                                execute=True, safety=SAFE)
        self.assertFalse(any(" servo " in c[-1] for c in self.calls))

    def test_live_dispatch_uses_same_arm_schema(self):
        with patch("scripts.real_robot_link.time.sleep"):
            result = self.link.apply_arm(ARM, duration_s=.5, execute=True, safety=SAFE)
        self.assertFalse(result["dry_run"])
        self.assertNotIn("--dry-run", self.calls[-1][-1])
        self.assertFalse(result["motion_confirmed"])

    def test_version_mismatch_blocks(self):
        self.link.control_sha256 = "b" * 64
        with self.assertRaises(LinkError):
            self.link.apply_arm(ARM, duration_s=.5)
        self.assertEqual(len(self.calls), 1)

    def test_bad_camera_blocks_before_command(self):
        self.link.http = lambda *a, **k: Response(b"not JPEG")
        with self.assertRaises(LinkError):
            self.link.apply_arm(ARM, duration_s=.5)
        self.assertFalse(any(" servo " in c[-1] for c in self.calls))

    def test_boolean_and_nan_are_not_servo_values(self):
        for action, duration in [(dict(ARM, pulse=True), .5), (dict(ARM, servo_id=True), .5),
                                 (ARM, float("nan")), (ARM, True)]:
            with self.subTest(action=action, duration=duration), self.assertRaises(ValueError):
                self.link.apply_arm(action, duration_s=duration)

    def test_observation_has_no_fake_top_or_exposure_time(self):
        obs = self.link.observe()
        self.assertFalse(obs["top_rgb_available"])
        self.assertNotIn("top_rgb", obs)
        self.assertFalse(obs["camera_calibrated_for_sim_policy"])
        self.assertNotIn("joint_positions", obs)
        self.assertIn("NOT exposure", obs["timestamp_source"])

    def test_timeout_is_not_retried_and_attempt_is_preserved(self):
        original = self.link.run

        def run(args, **kwargs):
            if " servo " in args[-1]:
                self.calls.append(args)
                raise subprocess.TimeoutExpired(args, 15)
            return original(args, **kwargs)

        self.link.run = run
        with self.assertRaises(subprocess.TimeoutExpired):
            self.link.apply_arm(ARM, duration_s=.5)
        self.assertEqual(sum(" servo " in c[-1] for c in self.calls), 1)
        self.assertEqual(self.link.history[0]["delivery_outcome"], "unknown")


if __name__ == "__main__":
    unittest.main()
