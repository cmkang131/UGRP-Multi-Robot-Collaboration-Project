# Experimental physical Solo adapter

Target: ras2 at 192.168.137.11; red 30 mm cube. The published Solo release supplies
survey, approach, alignment and the seg5 ACT step4000 grasp model. Inference runs
on the Windows laptop; the owned Pi process supplies images and drives hardware.

Current status: the camera-history crash is fixed. The latest recorded ras2 trial
failed alignment with `quality_exhausted` and never reached ACT. There is no
verified physical pick success. Camera geometry and pulse travel still need real
measurements. The cube adapter removes the training rectangle's unnecessary
wide-face orbit only after the original visual quality, yaw, bearing and range
conditions pass. It does not relax those conditions or force ACT handover.

From the project root, first check without movement:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\outputs\ras2-solo-pipeline\run_ras2_solo.ps1 -RobotAddress 192.168.137.11 -RobotName ras2 -Target red
```

Collect labelled measurements next, with the robot on a clear, level floor:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\outputs\ras2-solo-pipeline\run_ras2_solo.ps1 -RobotAddress 192.168.137.11 -RobotName ras2 -Target red -Calibrate -Seconds 600
```

The SSH account is prompted; hostname and login account need not match.
The calibration moves the arm through the published postures. Mark the base
origin halfway between the front and rear wheel axles, midway across the robot.
Place the cube center at five locations, measured from that origin:

| Step | Forward (cm) | Left (cm) |
|---|---:|---:|
| 1 | 20 | 0 |
| 2 | 30 | 0 |
| 3 | 45 | 0 |
| 4 | 30 | 10 |
| 5 | 30 | -10 |

At each prompt, remove hands and press Enter. Keep the base still for all camera
captures. Remove other red objects. Afterwards, each optional drive measurement
requires typing PULSE: it sends one 0.10 s pulse at speed 35. Mark the initial
base position and heading; measure forward/left displacement (cm) and rotation
(degrees, counterclockwise positive). Enter `x_cm,y_cm,yaw_degrees`, or `skip`.
Keep the floor clear; Ctrl+C closes the owned hardware session.

Data is saved under `calibrations/<hostname>/<timestamp>/samples.json` with JPEGs.
This is **raw calibration evidence**, not an automatically fitted or applied
camera/drive profile. Skipped or incomplete measurements remain explicit. The
ordinary `-Execute` path still uses uncalibrated simulation geometry; collecting
data does not make it calibrated. Fitting and physical validation remain pending.

Offline checks: `source/verify_live_history.py`, `source/cube_alignment.py` and
`source/verify_calibration.py`. These use saved frames and fake transports and
send no physical hardware commands.
