"""Source-traced MasterPi geometry for the visual remodel v3.

This module is *new* and deliberately does not edit ``sim/masterpi_geometry.py``
or ``sim/masterpi_dynamics_v2.py``: both files are hashed by registered
execution bundles, so v2 must stay byte-identical.

Frames and units
----------------
All constants are metres.  ``x`` is forward, ``y`` left, ``z`` up.  ``*_X_M``
values are measured from the axle midpoint (the v2 ``robot`` body origin in the
horizontal plane).  ``*_Z_FLOOR_M`` values are heights above the floor.  Link
local values (``*_ALONG_M`` / ``*_UP_M``) are measured along the link from the
named joint axis with the arm pointing forward.

Source classes (every value is tagged in :data:`SOURCES`)
---------------------------------------------------------
``official``
    A number printed by Hiwonder (product specification table, dimension
    drawing label, module/servo datasheet image).
``public_measured``
    Scaled by us from an official Hiwonder drawing using its own printed
    dimensions as the ruler (scale error about +/-1 %, i.e. +/-1-2 mm).
``photo_estimate``
    Read from official photos/renders without a ruler; appearance only.
``real_fit``
    Anchored to REAL ugrp1 data already used by the simulator (camera mount).
``controller``
    Hiwonder SDK / physical pickup-controller kinematics (``harness.real_geometry``).

The main drawing is Hiwonder's MasterPi "Dimensional Diagram"
(https://www.hiwonder.com/products/masterpi, image ``masterpi_01173667-...jpg``,
1200x1200 px).  Its printed dimensions give a consistent scale of 2.357 px/mm
(343 mm -> 806.5 px, 215 mm -> 505 px, 162 mm -> 382 px, 185 mm -> 438 px,
65 mm -> 153.5 px).  Pixel anchors: floor y=991.5 px, axle midpoint x=880 px
(wheel centres 740 / 1020 px) in the side view; robot centreline x=272.8 px in
the front view.
"""
from __future__ import annotations

from typing import Final

GEOMETRY_VERSION: Final = "masterpi-geometry-v3-20260928"

DRAWING_URL: Final = "https://www.hiwonder.com/products/masterpi"
DRAWING_IMAGE: Final = (
    "https://cdn.shopify.com/s/files/1/0084/2799/5187/files/"
    "masterpi_01173667-020d-4baa-8ec8-6ff4a45b6220.jpg?v=1716200111"
)
DRAWING_PX_PER_MM: Final = 2.357
DRAWING_FLOOR_Y_PX: Final = 991.5
DRAWING_AXLE_MID_X_PX: Final = 880.0


def drawing_side_to_m(x_px: float, y_px: float) -> tuple[float, float]:
    """Side-view drawing pixel -> (x forward of axle midpoint, z above floor) m."""
    return (
        (DRAWING_AXLE_MID_X_PX - x_px) / DRAWING_PX_PER_MM / 1000.0,
        (DRAWING_FLOOR_Y_PX - y_px) / DRAWING_PX_PER_MM / 1000.0,
    )


# ---------------------------------------------------------------- envelope
OFFICIAL_TOTAL_LENGTH_M: Final = 0.185
OFFICIAL_TOTAL_WIDTH_M: Final = 0.162
OFFICIAL_TOTAL_HEIGHT_M: Final = 0.343
OFFICIAL_WHEEL_DIAMETER_M: Final = 0.065
OFFICIAL_WHEEL_WIDTH_M: Final = 0.030           # drawing label "30mm" (v2 uses 31 mm)
OFFICIAL_COVER_TOP_Z_FLOOR_M: Final = 0.101      # drawing label "101mm"
OFFICIAL_SHOULDER_TO_TOP_M: Final = 0.215        # drawing label "215mm" (arm straight up)

# ------------------------------------------------------------ lower chassis
# Dark inverted-U sheet-metal body.  The drawing shows the front plate at the
# 185 mm length line (x=658 px), i.e. the chassis spans the full robot length
# and is NOT a 120 mm tray between the axles as in v2.
CHASSIS_LENGTH_M: Final = 0.185
CHASSIS_FRONT_PLATE_WIDTH_M: Final = 0.087       # front view 170..375 px
CHASSIS_OUTER_WIDTH_M: Final = 0.093             # incl. side flanges 163..382 px
CHASSIS_BOTTOM_Z_FLOOR_M: Final = 0.0168         # side view y=952 px
CHASSIS_TOP_Z_FLOOR_M: Final = 0.0500            # side view y=873.75 px
CHASSIS_END_CHAMFER_M: Final = 0.010             # photo estimate (bevelled ends)

# ------------------------------------------- arm-base box + ultrasonic mount
# Hiwonder ships the arm pre-assembled on a dark sheet-metal box that holds the
# ID6 yaw servo; the glowing ultrasonic module is screwed into the FRONT FACE
# of that box (packing-list image "MasterPi robotic arm (assembled)").
ARM_BOX_REAR_X_M: Final = 0.0098                 # side view x=857 px
ARM_BOX_FRONT_X_M: Final = 0.0769                # side view x=698.75 px
ARM_BOX_WIDTH_M: Final = 0.0549                  # front view 209..338 px
ARM_BOX_BOTTOM_Z_FLOOR_M: Final = CHASSIS_TOP_Z_FLOOR_M
ARM_BOX_TOP_Z_FLOOR_M: Final = 0.0802            # side view y=802.5 px

SONAR_BOARD_WIDTH_M: Final = 0.0456              # official module 45.6 x 28.5 mm
SONAR_BOARD_HEIGHT_M: Final = 0.0285
SONAR_TRANSDUCER_SPACING_M: Final = 0.0267       # official module drawing (26.7 mm)
SONAR_TRANSDUCER_DIAMETER_M: Final = 0.0160      # module drawing 15.7 mm / MasterPi 16.6 mm
SONAR_CENTER_Z_FLOOR_M: Final = 0.0617           # front view circle centres y=846 px
SONAR_FACE_X_M: Final = 0.0880                   # side view protrusion front x=672.5 px
SONAR_PROTRUSION_M: Final = SONAR_FACE_X_M - ARM_BOX_FRONT_X_M
SONAR_CENTER_Y_M: Final = 0.0                    # centred (front view 273 px vs 272.8 px)
SONAR_PITCH_DEG: Final = 0.0                     # transducer axes drawn horizontal
SONAR_LED_SLOT_Z_FLOOR_M: Final = 0.0703         # 4-hole slot above transducers
OFFICIAL_SONAR_BEAM_ANGLE_DEG: Final = 15.0      # "Measurement angle 15 degrees"

# v2 values kept for comparison / migration notes only.
V2_SONAR_CENTER_Z_FLOOR_M: Final = 0.054
V2_SONAR_CENTER_X_M: Final = 0.078
V2_SONAR_SPACING_M: Final = 0.034
V2_SONAR_DIAMETER_M: Final = 0.020

# ----------------------------------------------------------- yaw / shoulder
YAW_AXIS_X_M: Final = 0.0482                     # horn 767.75 px / shoulder hub 765 px
YAW_SERVO_TOP_Z_FLOOR_M: Final = 0.0930          # side view y=772.5 px
YAW_SERVO_FRONT_FROM_AXIS_M: Final = 0.0111      # ID6 body front end 741 px vs axis
TURNTABLE_TOP_Z_FLOOR_M: Final = 0.0993          # U-bracket floor y=757.5 px
SHOULDER_AXIS_Z_FLOOR_M: Final = 0.1277          # side view y=690.5 px (215 mm datum)
SHOULDER_BRACKET_TOP_Z_FLOOR_M: Final = 0.1406   # rounded top of base U-bracket
SHOULDER_BRACKET_OUTER_WIDTH_M: Final = 0.0552   # front view 208..338 px
SHOULDER_BRACKET_BOTTOM_LEN_M: Final = 0.0357    # trapezoid base, side view
V2_YAW_AXIS_X_M: Final = 0.0
V2_SHOULDER_AXIS_Z_FLOOR_M: Final = 0.1255       # 32.5 + 62.5 + 30.5 mm

# --------------------------------------------------------------- arm links
DRAWING_UPPER_ARM_M: Final = 0.0577              # shoulder 690.5 px -> elbow 554.5 px
DRAWING_FOREARM_M: Final = 0.0624                # elbow 554.5 px -> wrist 407.5 px
DRAWING_WRIST_TO_TIP_M: Final = 0.0940           # wrist -> closed finger tip 186 px
CONTROLLER_UPPER_ARM_M: Final = 0.065            # Hiwonder SDK l2 / harness LINK_2_CM
CONTROLLER_FOREARM_M: Final = 0.062              # Hiwonder SDK l3 / harness LINK_3_CM
CONTROLLER_TOOL_M: Final = 0.100                 # Hiwonder SDK l4 ("claw fully closed")
ARM_FRAME_OUTER_WIDTH_M: Final = 0.0414          # front view 225..322.5 px
ARM_PLATE_WIDTH_M: Final = 0.0198                # side view link plate 46.7/2.357
ARM_PLATE_THICKNESS_M: Final = 0.0020            # photo estimate (sheet aluminium)

# ------------------------------------------------------------------ servos
# Hiwonder datasheets (official): LD-1501MG 40 x 20 x 40.5 mm (45.5 with spline,
# 54.4 with ears); LFD-01M 32.5 x 12 x 29.85 mm overall.  The MasterPi spec
# table lists exactly these two types; the drawing shows the large type at
# ID6/ID5 and the small type at ID4/ID3/ID1.  Newer listings show an LDX-218
# (same 40 x 20 x 40.5 mm envelope class) at ID5.
LD1501_BODY_M: Final = (0.0400, 0.0200, 0.0405)  # length, width, height(shaft axis)
LD1501_EAR_LENGTH_M: Final = 0.0544
LD1501_SHAFT_FROM_END_M: Final = 0.0097           # shoulder: 127.7 - 118.0 mm
LFD01M_BODY_M: Final = (0.0232, 0.0120, 0.0257)   # length, width, height w/o spline
LFD01M_EAR_LENGTH_M: Final = 0.0325
SHOULDER_SERVO_ALONG_M: Final = (-0.0092, 0.0300)  # front view 118.5..157.7 mm
UPPER_ARM_CAP_ALONG_M: Final = 0.0352              # U-cap above ID5, 162.9 mm
ELBOW_SERVO_ALONG_M: Final = (-0.0066, 0.0168)     # ID4 body vs elbow axis
WRIST_SERVO_ALONG_M: Final = (-0.0159, 0.0117)     # ID3 body vs wrist axis

# ----------------------------------------------------------------- gripper
GRIPPER_BASE_PLATE_ALONG_M: Final = 0.0223        # grey bracket floor 355 px
GRIPPER_BRACKET_UP_M: Final = (-0.0166, 0.0106)   # bracket extent across the tool axis
GRIPPER_BRACKET_TOP_ALONG_M: Final = 0.0470       # bracket sides reach 296 px
GRIPPER_SERVO_ALONG_M: Final = (0.0323, 0.0445)   # ID1 LFD-01M, side view
GRIPPER_SERVO_BELOW_M: Final = (0.0074, 0.0350)   # below the tool axis (arm forward)
FINGER_PAD_LENGTH_M: Final = 0.0143               # orange rubber tip 186..220 px
FINGER_PLATE_THICKNESS_M: Final = 0.0037          # finger edge-on 756..765 px
FINGER_OPEN_SPAN_M: Final = 0.0467                # front view claw outline 217.5..327.5 px

# ------------------------------------------------------------------ camera
# Stock Hiwonder HD wide-angle camera HBVCAM-V2101 (official: module 30 x 25 x
# 25 mm, 640x480, 170 deg).  ugrp1's profile is an icspring fisheye unit; its
# REAL-fitted pose is kept unchanged (see sim.masterpi_camera_profile).
CAMERA_MODULE_M: Final = (0.030, 0.025, 0.025)
DRAWING_CAMERA_LENS_ALONG_M: Final = 0.0530       # lens front vs wrist axis
DRAWING_CAMERA_LENS_UP_M: Final = 0.0278          # lens axis above tool axis
CAMERA_LENS_DIAMETER_M: Final = 0.0143
CAMERA_LENS_LENGTH_M: Final = 0.0165              # barrel 455..640 px -> 19.6 incl cap

# --------------------------------------------------- electronics & cover
# The Raspberry Pi sits with its long 85 mm side along x and the USB/Ethernet
# ports facing the rear (official rear assembly photo, step 6).  v2 rotated it.
PI_BOARD_M: Final = (0.085, 0.056, 0.0016)
PI_BOARD_CENTER_X_M: Final = -0.0405
PI_BOARD_Z_FLOOR_M: Final = 0.0610                # side view PCB 843..853 px
EXPANSION_BOARD_Z_FLOOR_M: Final = 0.0740         # photo estimate (HAT stack)
PI_PORTS_REAR_X_M: Final = -0.0860                # side view ports x=1083 px
COVER_FRONT_X_M: Final = 0.0035                   # top plate 871.7 px
COVER_REAR_X_M: Final = -0.0856                   # top plate 1081.7 px
COVER_TOP_HALF_WIDTH_M: Final = 0.0394            # front view top edge
COVER_SIDE_BOTTOM_HALF_WIDTH_M: Final = 0.0472    # side panels flare outward
COVER_SIDE_BOTTOM_Z_FLOOR_M: Final = 0.0679       # side panel lower edge 831.7 px
COVER_SIDE_REAR_X_M: Final = -0.0733
COVER_WINDOW_Z_FLOOR_M: Final = (0.0740, 0.0880)  # triangular windows
STANDOFF_X_M: Final = (-0.0170, -0.0768)          # copper M4x50 columns
STANDOFF_HALF_SPAN_Y_M: Final = 0.0332
STANDOFF_DIAMETER_M: Final = 0.0070               # M4 hex column across flats

# ------------------------------------------------------------------ wheels
WHEEL_ROLLER_COUNT: Final = 9                     # drawing side outline, photo estimate
WHEEL_HUB_DIAMETER_M: Final = 0.0389              # grey side plate circle
WHEEL_SPOKE_COUNT: Final = 10                     # drawing hub
DRAWING_TRACK_M: Final = 0.1299                   # wheel centres 120.5 / 426.5 px (v2 131)
DRAWING_WHEELBASE_M: Final = 0.1188               # 740 / 1020 px (v2 120)

# ------------------------------------------------------------------ colours
RGBA: Final = {
    "gunmetal": (0.30, 0.31, 0.33, 1.0),     # chassis, arm-base box, cover
    "gunmetal_edge": (0.20, 0.21, 0.22, 1.0),
    "orange_anodized": (0.93, 0.52, 0.16, 1.0),
    "servo_black": (0.045, 0.047, 0.052, 1.0),
    "silver": (0.66, 0.68, 0.70, 1.0),       # gripper plates, horns
    "copper": (0.80, 0.52, 0.28, 1.0),
    "rubber_orange": (0.98, 0.43, 0.10, 1.0),
    "hub_grey": (0.42, 0.43, 0.45, 1.0),
    "pcb_green": (0.05, 0.33, 0.13, 1.0),
    "pcb_black": (0.06, 0.07, 0.08, 1.0),
    "sonar_can": (0.80, 0.82, 0.84, 1.0),
    "sonar_mesh": (0.10, 0.11, 0.12, 1.0),
    "hole": (0.02, 0.02, 0.025, 1.0),
    "lens": (0.02, 0.03, 0.05, 1.0),
    "port_metal": (0.70, 0.72, 0.74, 1.0),
    "port_blue": (0.10, 0.30, 0.80, 1.0),
}

# ------------------------------------------------------------ provenance
# name -> (value, source class, where it comes from)
SOURCES: Final[dict[str, tuple[object, str, str]]] = {
    "OFFICIAL_TOTAL_LENGTH_M": (OFFICIAL_TOTAL_LENGTH_M, "official", "product spec 185*162*343 mm"),
    "OFFICIAL_TOTAL_WIDTH_M": (OFFICIAL_TOTAL_WIDTH_M, "official", "product spec"),
    "OFFICIAL_TOTAL_HEIGHT_M": (OFFICIAL_TOTAL_HEIGHT_M, "official", "product spec / drawing 343 mm"),
    "OFFICIAL_WHEEL_DIAMETER_M": (OFFICIAL_WHEEL_DIAMETER_M, "official", "drawing label 65 mm"),
    "OFFICIAL_WHEEL_WIDTH_M": (OFFICIAL_WHEEL_WIDTH_M, "official", "drawing label 30 mm"),
    "OFFICIAL_COVER_TOP_Z_FLOOR_M": (OFFICIAL_COVER_TOP_Z_FLOOR_M, "official", "drawing label 101 mm"),
    "OFFICIAL_SHOULDER_TO_TOP_M": (OFFICIAL_SHOULDER_TO_TOP_M, "official", "drawing label 215 mm"),
    "CHASSIS_LENGTH_M": (CHASSIS_LENGTH_M, "public_measured", "drawing: front plate on the 185 mm line"),
    "CHASSIS_FRONT_PLATE_WIDTH_M": (CHASSIS_FRONT_PLATE_WIDTH_M, "public_measured", "drawing front view"),
    "CHASSIS_OUTER_WIDTH_M": (CHASSIS_OUTER_WIDTH_M, "public_measured", "drawing front view"),
    "CHASSIS_BOTTOM_Z_FLOOR_M": (CHASSIS_BOTTOM_Z_FLOOR_M, "public_measured", "drawing side view"),
    "CHASSIS_TOP_Z_FLOOR_M": (CHASSIS_TOP_Z_FLOOR_M, "public_measured", "drawing side view"),
    "CHASSIS_END_CHAMFER_M": (CHASSIS_END_CHAMFER_M, "photo_estimate", "assembly step 1/4 renders"),
    "ARM_BOX_REAR_X_M": (ARM_BOX_REAR_X_M, "public_measured", "drawing side view"),
    "ARM_BOX_FRONT_X_M": (ARM_BOX_FRONT_X_M, "public_measured", "drawing side view"),
    "ARM_BOX_WIDTH_M": (ARM_BOX_WIDTH_M, "public_measured", "drawing front view"),
    "ARM_BOX_TOP_Z_FLOOR_M": (ARM_BOX_TOP_Z_FLOOR_M, "public_measured", "drawing side view"),
    "SONAR_BOARD_WIDTH_M": (SONAR_BOARD_WIDTH_M, "official", "glowing ultrasonic spec 45.6*28.5 mm"),
    "SONAR_BOARD_HEIGHT_M": (SONAR_BOARD_HEIGHT_M, "official", "glowing ultrasonic spec"),
    "SONAR_TRANSDUCER_SPACING_M": (SONAR_TRANSDUCER_SPACING_M, "public_measured", "module drawing scaled by 45.6 mm; MasterPi drawing 26.4 mm"),
    "SONAR_TRANSDUCER_DIAMETER_M": (SONAR_TRANSDUCER_DIAMETER_M, "public_measured", "module drawing 15.7 mm; MasterPi drawing 16.6 mm"),
    "SONAR_CENTER_Z_FLOOR_M": (SONAR_CENTER_Z_FLOOR_M, "public_measured", "MasterPi drawing front view, circle centres y=846 px"),
    "SONAR_FACE_X_M": (SONAR_FACE_X_M, "public_measured", "MasterPi drawing side view, x=672.5 px"),
    "SONAR_CENTER_Y_M": (SONAR_CENTER_Y_M, "public_measured", "MasterPi drawing front view"),
    "SONAR_PITCH_DEG": (SONAR_PITCH_DEG, "public_measured", "transducer axes horizontal in side view"),
    "OFFICIAL_SONAR_BEAM_ANGLE_DEG": (OFFICIAL_SONAR_BEAM_ANGLE_DEG, "official", "glowing ultrasonic spec (half/full angle not stated)"),
    "YAW_AXIS_X_M": (YAW_AXIS_X_M, "public_measured", "drawing side view, yaw horn / shoulder hub"),
    "YAW_SERVO_TOP_Z_FLOOR_M": (YAW_SERVO_TOP_Z_FLOOR_M, "public_measured", "drawing side view"),
    "TURNTABLE_TOP_Z_FLOOR_M": (TURNTABLE_TOP_Z_FLOOR_M, "public_measured", "drawing side view"),
    "SHOULDER_AXIS_Z_FLOOR_M": (SHOULDER_AXIS_Z_FLOOR_M, "public_measured", "drawing 215 mm datum line y=690.5 px"),
    "SHOULDER_BRACKET_OUTER_WIDTH_M": (SHOULDER_BRACKET_OUTER_WIDTH_M, "public_measured", "drawing front view"),
    "DRAWING_UPPER_ARM_M": (DRAWING_UPPER_ARM_M, "public_measured", "drawing joint centres"),
    "DRAWING_FOREARM_M": (DRAWING_FOREARM_M, "public_measured", "drawing joint centres"),
    "DRAWING_WRIST_TO_TIP_M": (DRAWING_WRIST_TO_TIP_M, "public_measured", "drawing wrist -> tip"),
    "CONTROLLER_UPPER_ARM_M": (CONTROLLER_UPPER_ARM_M, "controller", "Hiwonder SDK ArmIK l2=6.50 cm; harness LINK_2_CM"),
    "CONTROLLER_FOREARM_M": (CONTROLLER_FOREARM_M, "controller", "Hiwonder SDK ArmIK l3=6.20 cm; harness LINK_3_CM"),
    "CONTROLLER_TOOL_M": (CONTROLLER_TOOL_M, "controller", "Hiwonder SDK ArmIK l4=10.00 cm"),
    "ARM_FRAME_OUTER_WIDTH_M": (ARM_FRAME_OUTER_WIDTH_M, "public_measured", "drawing front view"),
    "ARM_PLATE_WIDTH_M": (ARM_PLATE_WIDTH_M, "public_measured", "drawing side view"),
    "ARM_PLATE_THICKNESS_M": (ARM_PLATE_THICKNESS_M, "photo_estimate", "product renders"),
    "LD1501_BODY_M": (LD1501_BODY_M, "official", "LD-1501MG datasheet 40*20*40.5 mm"),
    "LFD01M_BODY_M": (LFD01M_BODY_M, "official", "LFD-01M datasheet 32.5*12*29.85 mm overall"),
    "SHOULDER_SERVO_ALONG_M": (SHOULDER_SERVO_ALONG_M, "public_measured", "drawing front view"),
    "ELBOW_SERVO_ALONG_M": (ELBOW_SERVO_ALONG_M, "public_measured", "drawing front view"),
    "WRIST_SERVO_ALONG_M": (WRIST_SERVO_ALONG_M, "public_measured", "drawing front view"),
    "GRIPPER_BASE_PLATE_ALONG_M": (GRIPPER_BASE_PLATE_ALONG_M, "public_measured", "drawing side view"),
    "GRIPPER_SERVO_ALONG_M": (GRIPPER_SERVO_ALONG_M, "public_measured", "drawing side view"),
    "GRIPPER_SERVO_BELOW_M": (GRIPPER_SERVO_BELOW_M, "public_measured", "drawing side view"),
    "FINGER_PAD_LENGTH_M": (FINGER_PAD_LENGTH_M, "public_measured", "drawing side view"),
    "FINGER_OPEN_SPAN_M": (FINGER_OPEN_SPAN_M, "public_measured", "drawing front view"),
    "CAMERA_MODULE_M": (CAMERA_MODULE_M, "official", "HBVCAM-V2101 module 30*25*25 mm"),
    "DRAWING_CAMERA_LENS_ALONG_M": (DRAWING_CAMERA_LENS_ALONG_M, "public_measured", "drawing side view (stock camera)"),
    "DRAWING_CAMERA_LENS_UP_M": (DRAWING_CAMERA_LENS_UP_M, "public_measured", "drawing side view (stock camera)"),
    "PI_BOARD_M": (PI_BOARD_M, "official", "Raspberry Pi 4B/5 board 85*56 mm"),
    "PI_BOARD_Z_FLOOR_M": (PI_BOARD_Z_FLOOR_M, "public_measured", "drawing side view"),
    "EXPANSION_BOARD_Z_FLOOR_M": (EXPANSION_BOARD_Z_FLOOR_M, "photo_estimate", "assembly step 4"),
    "COVER_FRONT_X_M": (COVER_FRONT_X_M, "public_measured", "drawing side view"),
    "COVER_REAR_X_M": (COVER_REAR_X_M, "public_measured", "drawing side view"),
    "COVER_TOP_HALF_WIDTH_M": (COVER_TOP_HALF_WIDTH_M, "public_measured", "drawing front view"),
    "COVER_SIDE_BOTTOM_HALF_WIDTH_M": (COVER_SIDE_BOTTOM_HALF_WIDTH_M, "public_measured", "drawing front view"),
    "STANDOFF_X_M": (STANDOFF_X_M, "public_measured", "drawing side view"),
    "STANDOFF_HALF_SPAN_Y_M": (STANDOFF_HALF_SPAN_Y_M, "public_measured", "drawing front view"),
    "WHEEL_ROLLER_COUNT": (WHEEL_ROLLER_COUNT, "photo_estimate", "drawing wheel outline"),
    "WHEEL_SPOKE_COUNT": (WHEEL_SPOKE_COUNT, "public_measured", "drawing hub"),
    "DRAWING_TRACK_M": (DRAWING_TRACK_M, "public_measured", "drawing front view wheel centres"),
    "DRAWING_WHEELBASE_M": (DRAWING_WHEELBASE_M, "public_measured", "drawing side view wheel centres"),
    "RGBA": (RGBA, "photo_estimate", "official product renders"),
}

# Values only the physical ugrp1 robot can settle.  Keep this list short and
# actionable: each entry says what to measure and why it matters.
MEASURE_ON_ROBOT: Final = (
    ("sonar_center_height_mm", "floor to the centre of the two transducers", "drawing 61.7, v2 54"),
    ("sonar_face_forward_mm", "axle midpoint to the transducer front face", "drawing 88.0, v2 84"),
    ("sonar_pitch_deg", "tilt of the transducer axes (level = 0)", "drawing 0"),
    ("yaw_axis_forward_mm", "axle midpoint to the arm yaw (ID6) axis", "drawing 48.2, v2 0"),
    ("shoulder_axis_height_mm", "floor to the ID5 shoulder axis", "drawing 127.7, v2 125.5"),
    ("upper_arm_mm", "ID5 axis to ID4 axis", "drawing 57.7, SDK/v2 65"),
    ("forearm_mm", "ID4 axis to ID3 axis", "drawing 62.4, SDK/v2 62"),
    ("wrist_to_closed_tip_mm", "ID3 axis to the closed finger tip", "drawing 94.0, SDK 100"),
    ("camera_lens_offset_mm", "lens centre along the tool / above the tool axis from ID3", "stock drawing 53/28, ugrp1 fit 67/13.6"),
    ("camera_model", "camera board/lens model on ugrp1 (stock HBVCAM or icspring)", "profile says icspring fisheye"),
    ("wheel_track_mm", "left-right wheel centre distance", "drawing 129.9, v2 131"),
    ("wheelbase_mm", "front-rear axle distance", "drawing 118.8, v2 120"),
    ("wheel_width_mm", "mecanum wheel width", "drawing 30, v2 31"),
    ("chassis_length_mm", "front plate to rear plate of the dark chassis", "drawing 185, v2 tray 120"),
    ("shoulder_servo_model", "label on ID5 (LD-1501MG or LDX-218)", "spec table LD-1501MG, newer photos LDX-218"),
)
