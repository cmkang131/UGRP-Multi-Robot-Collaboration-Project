"""Command-only gravity-droop compensation of the camera elevation. OPTION, default OFF. Refs #216.

The detector's camera pitch is forward kinematics of the COMMANDED pulses plus a constant bias (``wall_probe.SEED_BIAS``).
The servos hold the pose with a finite stiffness, so each pitch joint sags by (gravity torque on it) / kp and the
camera elevation error (rendered camera minus FK) depends on the pose (``diag_sag.py``: -1.99 .. -0.44 deg unloaded).
A constant cannot be right at every pose.

Model (planar chain, the three pitch joints are parallel). With the absolute link angles of ``harness.visual_arm``
(shoulder ``phi1``, forearm ``phi2``, tool pitch ``phi3``), the horizontal lever arm of a link is ``cos(phi)``, and
the summed joint deflection, which is what tilts the camera, is linear in ``cos phi1, cos phi2, cos phi3``:

    unloaded   elevation_error = c0 + A cos(phi1) + B cos(phi2) + C cos(phi3)
    loaded     the same, plus  m * [ (L2 c1 + L3 c2 + l c3)/kp1 + (L3 c2 + l c3)/kp2 + l c3/kp3 ]

the second line being a point mass at the tool tip carried through the known link lengths and servo stiffnesses
(one free parameter ``m`` = weight of the carried object in newtons). Inputs: the commanded pulses and the own
gripper command (load) only. No ground truth, no recorded joint angle, no simulator state.

The coefficients are fitted by ``fit_sag.py`` on the exploration recording and validated on separate confirmation
recordings; they live in ``sag_coeffs.json`` next to this file. ``bias_rad`` replaces the constant seed bias when the
option is on; with the option off nothing here is called.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Mapping

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))
from harness.visual_arm import (GRIPPER_LINK_CM, LINK_2_CM, LINK_3_CM, PULSE_PER_DEGREE,  # noqa: E402
                                SERVO_DEVIATION)

COEFFS_PATH = HERE/'sag_coeffs.json'
KP_N_M_PER_RAD = (7.0, 6.0, 3.5)          # shoulder, elbow, wrist (sim/masterpi_dynamics_v2 actuators)
LEVERS_M = (LINK_2_CM/100, LINK_3_CM/100, GRIPPER_LINK_CM/100)


def link_cosines(servo: Mapping) -> np.ndarray:
    """cos of the three absolute link angles (shoulder, forearm, tool pitch), from the commanded pulses."""
    nom = lambda k: float(servo[k]) - SERVO_DEVIATION.get(k, 0)
    th3 = (nom(3) - 1500.)/PULSE_PER_DEGREE
    th4 = (nom(4) - 1500.)/PULSE_PER_DEGREE
    th5 = 90. - (nom(5) - 1500.)/PULSE_PER_DEGREE
    return np.cos(np.radians([th5, th5 - th4, th3 + th5 - th4]))


def design_row(servo: Mapping, loaded: bool) -> np.ndarray:
    """Row of the linear model: [1, c1, c2, c3, load term] (the load term is 0 when not loaded)."""
    c1, c2, c3 = link_cosines(servo)
    l1, l2, l3 = LEVERS_M
    k1, k2, k3 = KP_N_M_PER_RAD
    load = ((l1*c1 + l2*c2 + l3*c3)/k1 + (l2*c2 + l3*c3)/k2 + l3*c3/k3) if loaded else 0.
    return np.array([1., c1, c2, c3, math.degrees(load)])    # load term in degrees per newton


def load_coeffs(path: Path = COEFFS_PATH) -> np.ndarray:
    d = json.loads(Path(path).read_text())
    return np.array([d['c0_deg'], d['A_deg'], d['B_deg'], d['C_deg'], d['m_load_N']])


def elevation_error_deg(servo: Mapping, loaded: bool, coeffs: np.ndarray | None = None) -> float:
    """Predicted camera elevation error (rendered minus FK, degrees) from the commanded pose and own load state."""
    c = load_coeffs() if coeffs is None else np.asarray(coeffs, float)
    return float(design_row(servo, loaded) @ c)


def bias_rad(servo: Mapping, loaded: bool, coeffs: np.ndarray | None = None) -> float:
    """Elevation bias for ``markerless_probe.column_model``: the option's replacement of ``SEED_BIAS``."""
    return math.radians(elevation_error_deg(servo, loaded, coeffs))
