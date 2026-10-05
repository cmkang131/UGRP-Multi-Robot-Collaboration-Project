"""Finite SIM-arm to REAL bridge; dry-run by default, no autonomous mission.

Reuse SIM's {kind: arm, servo_id, pulse} command shape, but never its clock,
speed factor, world state, or camera calibration. No chassis conversion exists:
SIM velocities are not calibrated REAL PWM motor duties.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import ipaddress
import json
import math
from pathlib import Path
import re
import shlex
import subprocess
import time
from urllib.request import urlopen


class LinkError(RuntimeError):
    pass


class RealRobotLink:
    def __init__(self, *, host, user, identity, known_hosts, camera_url,
                 control_sha256, robot_id="r1", run=subprocess.run, http=urlopen):
        ipaddress.ip_address(host)
        if not re.fullmatch(r"[a-z_][a-z0-9_-]*", user):
            raise ValueError("invalid robot user")
        if robot_id not in ("r1", "r2", "r3"):
            raise ValueError("invalid robot identity")
        if not re.fullmatch(r"[0-9a-f]{64}", control_sha256):
            raise ValueError("pin the reviewed remote control SHA256")
        # Camera traffic stays on the existing local SSH tunnel.
        if not re.fullmatch(r"http://127\.0\.0\.1:[0-9]+/snapshot", camera_url):
            raise ValueError("use the local SSH snapshot tunnel")
        self.robot_id, self.camera_url = robot_id, camera_url
        self.control = f"/home/{user}/MasterPi/tools/masterpi_control.py"
        self.control_sha256 = control_sha256
        self.run, self.http = run, http
        self.history = []
        self.ssh = ["ssh", "-i", str(identity), "-o", "IdentitiesOnly=yes",
                    "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
                    "-o", "UserKnownHostsFile=" + str(known_hosts),
                    "-o", "ConnectTimeout=8", f"{user}@{host}"]

    def remote(self, args):
        # Each remote command is finite; failures are never silently retried.
        result = self.run(self.ssh + [shlex.join(args)], capture_output=True,
                          text=True, timeout=15, check=False)
        if result.returncode:
            raise LinkError((result.stderr or result.stdout).strip() or "SSH failed")
        return result.stdout.strip()

    def check_version(self):
        text = self.remote(["sha256sum", self.control])
        if not text or text.split()[0] != self.control_sha256:
            raise LinkError("remote control changed; review before issuing commands")

    def observe(self):
        start = time.monotonic()
        with self.http(self.camera_url, timeout=5) as response:
            if response.status != 200:
                raise LinkError("camera did not return HTTP 200")
            jpeg = response.read(2_000_001)
        if (len(jpeg) > 2_000_000 or not jpeg.startswith(b"\xff\xd8")
                or not jpeg.endswith(b"\xff\xd9")):
            raise LinkError("invalid or oversized JPEG")
        return {"robot_id": self.robot_id, "camera": "real_own_raw",
                "image": base64.b64encode(jpeg).decode("ascii"),
                "sha256": hashlib.sha256(jpeg).hexdigest(),
                "clock_domain": "monotonic",
                "request_at_s": start, "received_at_s": time.monotonic(),
                "timestamp_source": "laptop HTTP interval, NOT exposure timestamp",
                "camera_calibrated_for_sim_policy": False,
                "top_rgb_available": False,
                "command_history": list(self.history)}

    def probe(self):
        self.check_version()
        value = json.loads(self.remote(["python3", self.control, "probe"]))
        voltage = value.get("battery_mv")
        if (value.get("ok") is not True or type(voltage) is not int
                or not 4500 <= voltage <= 9500):
            raise LinkError("invalid controller telemetry; live motion disabled")
        # This legacy protocol range is not a safe operating voltage calibration.
        return value

    @staticmethod
    def validate_arm(action, duration):
        if (not isinstance(action, dict)
                or set(action) != {"kind", "servo_id", "pulse"}
                or action["kind"] != "arm"):
            raise ValueError("only SIM arm commands supported; no mission/drive replay")
        if type(action["servo_id"]) is not int or action["servo_id"] not in (1, 3, 4, 5, 6):
            raise ValueError("invalid servo")
        if type(action["pulse"]) is not int or not 500 <= action["pulse"] <= 2500:
            raise ValueError("invalid protocol pulse")
        if (isinstance(duration, bool) or not isinstance(duration, (int, float))
                or not math.isfinite(duration) or not 0.1 <= duration <= 3):
            raise ValueError("invalid REAL duration")

    def apply_arm(self, action, *, duration_s, execute=False, safety=None):
        self.validate_arm(action, duration_s)
        self.check_version()
        # Check that a current camera request succeeds BEFORE a command.
        before = self.observe()
        if execute:
            self._check_safety(action, safety)
        args = ["python3", self.control]
        if not execute:
            args.append("--dry-run")
        args += ["servo", str(action["servo_id"]), str(action["pulse"]),
                 "--duration", str(duration_s)]
        submitted = time.monotonic()
        attempt = {"robot_id": self.robot_id, "action": dict(action),
                   "duration_s": duration_s, "submitted_at_s": submitted,
                   "dry_run": not execute, "motion_confirmed": False,
                   "delivery_outcome": "unknown"}
        self.history.append(attempt)
        reply = self.remote(args)
        attempt["delivery_outcome"] = "remote_process_exit_0"
        # Remote completion is not measured joint arrival. Capture only after
        # the requested transition interval; no autonomous follow-up is issued.
        if execute:
            time.sleep(duration_s)
        after = self.observe()
        return {"dry_run": not execute, "remote_reply": reply,
                "motion_confirmed": False, "before": before, "after": after}

    def _check_safety(self, action, safety):
        keys = {"robot_id", "servo_id", "pulse_min", "pulse_max",
                "battery_min_mv", "battery_max_mv", "operator_ready"}
        if not isinstance(safety, dict) or set(safety) != keys:
            raise LinkError("explicit operator safety profile required")
        lo, hi = safety["pulse_min"], safety["pulse_max"]
        if (safety["robot_id"] != self.robot_id
                or type(safety["servo_id"]) is not int
                or safety["servo_id"] != action["servo_id"]
                or safety["operator_ready"] is not True
                or type(lo) is not int or type(hi) is not int
                or not 500 <= lo <= action["pulse"] <= hi <= 2500):
            raise LinkError("action outside operator-approved mechanical limits")
        low, high = safety["battery_min_mv"], safety["battery_max_mv"]
        if (type(low) is not int or type(high) is not int
                or not 4500 <= low < high <= 9500):
            raise LinkError("hardware-specific operating voltage limits required")
        telemetry = self.probe()
        if not low <= telemetry["battery_mv"] <= high:
            raise LinkError("battery outside approved operating limits")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("observe", "probe", "arm"))
    parser.add_argument("--host", required=True)
    parser.add_argument("--user", default="ugrp1")
    parser.add_argument("--robot-id", default="r1")
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--known-hosts", type=Path, required=True)
    parser.add_argument("--camera-url", default="http://127.0.0.1:18080/snapshot")
    parser.add_argument("--control-sha256", required=True)
    parser.add_argument("--action-json")
    parser.add_argument("--duration-s", type=float, default=1.)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--safety-profile", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("output already exists; do not overwrite evidence")
    if args.execute and args.operation != "arm":
        parser.error("--execute applies only to an explicit arm action")
    args.output.mkdir(parents=True)
    receipt = {"schema": "ugrp.real_link_check.v1", "operation": args.operation,
               "robot_id": args.robot_id, "source_sha": None,
               "control_sha256": args.control_sha256, "ok": False,
               "mission_integration_complete": False}
    link = None
    try:
        receipt["source_sha"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[1],
            text=True, timeout=5).strip()
        link = RealRobotLink(host=args.host, user=args.user, identity=args.identity,
                             known_hosts=args.known_hosts, camera_url=args.camera_url,
                             control_sha256=args.control_sha256, robot_id=args.robot_id)
        if args.operation == "observe":
            link.check_version()
            receipt["observation"] = link.observe()
        elif args.operation == "probe":
            receipt["telemetry"] = link.probe()
        else:
            if not args.action_json:
                raise LinkError("--action-json is required")
            safety = json.loads(args.safety_profile.read_text(encoding="utf-8")) if args.safety_profile else None
            receipt["result"] = link.apply_arm(json.loads(args.action_json),
                duration_s=args.duration_s, execute=args.execute, safety=safety)
        receipt["ok"] = True
    except (Exception, KeyboardInterrupt) as exc:
        receipt["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        receipt["command_attempts"] = link.history if link else []
        (args.output / "result.json").write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in receipt.items() if k not in ("observation", "result")}, ensure_ascii=False))
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
