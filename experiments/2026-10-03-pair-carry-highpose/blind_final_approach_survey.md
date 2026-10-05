# Survey: target leaves eye-in-hand view in the final approach (blind last segment)

Date: 2026-10-04. Survey only; no project files changed.

## A. Classic visual servoing

1. Hutchinson, Hager, Corke (1996). A tutorial on visual servo control. IEEE T-RA 12(5):651-670.
   URL fetched: https://faculty.cc.gatech.edu/~seth/ResPages/pdfs/HutHagCor96.pdf (scanned; read via OCR). VERIFIED.
   - Look-then-move is the baseline: vision gives an estimate and the robot moves open loop. The final accuracy then depends directly on how accurate the visual sensor and the robot are.
   - Endpoint open-loop (EOL) systems see only the target. Endpoint closed-loop (ECL) systems see the target and the end-effector. ECL is less sensitive to calibration but adds field-of-view constraints "that cannot always be satisfied" (the paper's words).
   - Remedy for feature occlusion: observers that notice the features have disappeared and keep predicting where they are from motion seen earlier.
   - No numeric thresholds.

2. Chaumette & Hutchinson (2006/2007). Visual servo control Part I / Part II. IEEE RAM 13(4) / 14(1).
   URLs: https://faculty.cc.gatech.edu/~seth/ResPages/pdfs/ChaHut06.pdf and ChaHut07.pdf. VERIFIED.
   - Part I: in PBVS, some configurations make points leave the camera field of view.
   - Part II: visibility is handled in three ways:
     - feature choice in hybrid schemes;
     - IBVS<->PBVS switching on Lyapunov thresholds (Gans & Hutchinson 2003; Chesi et al. 2004 for FOV);
     - offline feature-trajectory planning that respects FOV, joint-limit and occlusion constraints (Mezouar & Chaumette 2002).
   - Neither part prescribes an open-loop hand-over at contact. The tutorials are about keeping features visible, not about acting once they are gone.

3. Kragic & Christensen (2002). Survey on visual servoing for manipulation. CVAP/KTH tech report.
   URL fetched: https://web.archive.org/web/2016/... (original http://www.nada.kth.se/~danik/VSpapers/report.pdf). VERIFIED.
   - "Open-loop robot control" estimates the pose once, then makes "blind" moves. It assumes the scene stays static after motion starts.
   - In the eye-in-hand configuration, the object to be manipulated is usually not in the camera's view.
   - The survey reports other people's systems, not Kragic's own method:
     - visual alignment, then a fixed "moves vertically down a few centimeters and grasps" step;
     - a stereo system that aligns the gripper plane and then performs a blind grasp;
     - Kalman-filter pose tracking to ride through occlusion.

4. Visibility-constraint family. Abstracts only, so UNVERIFIED for the mechanism.
   - Mezouar & Chaumette (2002), Path planning for robust image-based control, IEEE T-RA. https://inria.hal.science/inria-00352101 . Plans image-space trajectories so the object stays in the FOV.
   - Garcia-Aracil, Malis, Aracil-Santonja, Perez-Vidal (2005), Continuous visual servoing despite the changes of visibility in image features, IEEE T-RO 21(6). https://inria.hal.science/hal-04654343 . Lets features leave or enter the view and weights them so the control law stays continuous. It still needs enough features visible, so it does not help when there are 0 px.
   - Cherubini & Chaumette (2013), Visual navigation of a mobile robot with laser-based collision avoidance, IJRR. https://inria.hal.science/hal-00750623 . Keeps the scene visible by turning the camera pan. Not applicable to a fixed mount.

5. Folio & Cadenat (2008). A sensor-based controller able to treat total image loss and to guarantee non-collision during a vision-based navigation task. IROS.
   URL fetched: https://web.archive.org/web/2016/https://hal.archives-ouvertes.fr/hal-00603686/document. VERIFIED.
   - Covers total image loss on a mobile robot.
   - The image features and their depth z are rebuilt by analytically integrating the interaction-matrix ODE. It starts from the last visual measurement and uses the robot's own velocity inputs. Control continues on these estimated features until the goal.
   - The error grows mainly with feature-extraction noise (~1 px), encoder velocity delay and drift, and an inaccurately known sampling period. The error rises when the controller switches.
   - No explicit time or distance limit is given.

## B. Learned / closed-loop eye-in-hand grasping

6. Morrison, Corke, Leitner (2018). Closing the loop for robotic grasping (GG-CNN). RSS. Plus code dougsm/ggcnn_kinova_grasping.
   Sources read: arXiv 1804.05172 text and the code file ggcnn_kinova_grasping/scripts/kinova_closed_loop_grasp.py. VERIFIED. The IJRR 2020 version was not read.
   - The RealSense SR300 sits on the wrist about 80 mm above the fingertips.
   - Depth is unreliable below 150 mm, so they stop updating the grasp pose there. At that point the gripper is about 70 mm from the object.
   - In the code, `if d[2] > 0.150` updates the target. Otherwise the target is frozen at the last 3-sample moving average (`Averager(4,3)`), and the PBVS servo keeps driving to it from arm proprioception.
   - Stop and close when any of these holds: `CURR_Z < 0.01`, `CURR_Z - 0.01 < GOAL_Z`, or smoothed `force.z < -5.0`. Then wait 0.1 s, close the fingers, wait 0.5 s, and lift home.
   - Finger width is pre-shaped while the object is still seen (`CURR_Z < 0.200 and CURR_DEPTH > 80`). Width is re-estimated only above 0.25 m.
   - Success = the object is lifted back to the start height.
   - The paper says it cannot correct errors in the last 70 mm. Under injected kinematic noise the closed-loop success rate still drops (68-73% worst case vs 38% open loop).
   - Open-loop variant: one image from about 350 mm, then a pregrasp 170 mm above the grasp, then straight down until the grasp pose or a force-detected collision.

7. Haviland, Dayoub, Corke (2020). Control of the final-phase of closed-loop visual grasping using image-based visual servoing. arXiv 2001.05650. VERIFIED.
   - Depth-based closed-loop graspers must finish the last stage open loop.
   - They treat depth as invalid when the object is within 25 cm. The extracted text calls the camera "RealSense D15", rated 16 cm.
   - Below 25 cm they switch from PBVS to RGB-only IBVS. The goal SIFT feature layout is predicted from the last valid depth frame plus the planned grasp pose.
   - Features are filtered by ratio test, duplicate removal, loop constraint, fundamental-matrix RANSAC and a 20x20 grid. IBVS depth is fixed at 5 cm.
   - They grasp when the feature error is small enough.
   - Moving objects: 76.25% vs 0% for GG-CNN. The main failure was the object leaving the FOV.
   - It assumes the fingers do not occlude the object. Here it would also need the target visible at the grasp pose, which is not the case.

8. Viereck, ten Pas, Saenko, Platt (2017). Learning a visuomotor controller for real world robotic grasping using simulated depth images. CoRL. arXiv 1706.04652. VERIFIED.
   - Wrist SR300, about 5 Hz loop, z step 1 cm, step ratio 0.5.
   - The controller runs until depth shows an object within 14 cm of the sensor, or the hand is too close to the table.
   - Then it executes a predefined motion and closes the fingers. This is a direct precedent for a fixed blind final segment.

9. Levine, Pastor, Krizhevsky, Ibarz, Quillen (2016/2018). Learning hand-eye coordination for robotic grasping with deep learning and large-scale data collection. IJRR. arXiv 1603.02199. VERIFIED.
   - The camera is over the shoulder, not eye-in-hand.
   - Relevant mechanism 1: the network also gets an image I0 taken before the grasp, which "does not contain the gripper". This is a remembered pre-approach view.
   - Relevant mechanism 2: CEM servoing with two rules:
     - close the gripper when closing scores at least 90% of the best move;
     - raise the gripper when closing scores below 50% of the best move.
   - Success labels: gripper position reading > 1 cm (fingers not fully closed), plus a drop test that compares images before and after the drop.

10. Kalashnikov et al. (2018). QT-Opt. CoRL. arXiv 1806.10293. VERIFIED.
    - Over-the-shoulder RGB camera. The state includes gripper status and height.
    - Scripted termination: the gripper is closed, its height is above 0.13 m, and it is still commanded upward.
    - Success is a lift above a height plus a background-subtraction drop test.
    - Open and close are free actions, so regrasping emerges.

11. Burgess-Limerick, Lehnert, Leitner, Corke (2022). DGBench: an open-source, reproducible benchmark for dynamic grasping. arXiv 2204.13879. VERIFIED.
    - Modern closed-loop systems revert to open loop in the final phase up to contact, because of minimum sensor range, limited FOV and occlusion.
    - At grasp time a wrist camera typically sees the object only at the border of its view.
    - For static grasping, the fixed, shoulder and wrist mounts are all called suitable. The fix they propose, a multi-camera palm-area array, is a hardware change and not allowed here.

## C. Mobile manipulation and public code

12. Burgess-Limerick et al. (2022/ICRA 2023). An architecture for reactive mobile manipulation on-the-move. arXiv 2212.06991. VERIFIED.
    - Within dT = 0.1 m of the target, control switches to a final-phase PBVS grasp controller (kP = 5).
    - Monocular RGB gives the object centroid. That ray is intersected with a plane at a known object height to get 3D position. The same geometry works for a floor beam.
    - Their camera is a palm fisheye that keeps the object in view, which does not transfer to our fixed mount.

13. Hello Robot stretch_ros, `stretch_demos/nodes/grasp_object` and `stretch_funmap/src/stretch_funmap/manipulation_planning.py` (noetic). https://github.com/hello-robot/stretch_ros . VERIFIED code.
    - One 4 s head-camera scan gives the grasp target.
    - Pregrasp lift = target + 0.10 m. Then yaw, open, drive the base, extend.
    - The grasp move comes from the same scan, with +0.01 m added for finger compliance. Then close to width - 0.18, sleep 3 s, lift 0.10 m.
    - There is no re-observation and no grasp check: it always returns success. Treat it as a negative example.

14. Hello Robot stretch_visual_servoing, `visual_servoing_demo.py`. https://github.com/hello-robot/stretch_visual_servoing . VERIFIED code.
    - The gripper D405 keeps the object in view, so the approach is not blind.
    - When the fingertip ArUco markers are occluded and the toy is within z < 0.12 m, the code substitutes a fixed default fingertip position (`default_between_fingertips`). This is a stand-in model when sensing is lost.
    - Grasp is triggered when error < 0.02 m.
    - Success = effort < -14 and fingertip gap between 0.05 and 0.085 m.
    - "Lost" = gap < 0.038 m or target error > 0.10 m. Retract is capped at 60 cycles.

15. Yenamandra et al. (2023). HomeRobot: open-vocabulary mobile manipulation. arXiv 2306.11565. Code: facebookresearch/home-robot `src/home_robot/home_robot/manipulation/grasping.py` and `src/home_robot_hw/home_robot_hw/utils/grasping.py`. VERIFIED.
    - Gaze skill: get close and point the head camera at the object.
    - Heuristic top-down grasp from one point cloud: 0.5 cm voxels, top 10% of points.
    - Executed as a joint waypoint list: pregrasp -> back -> standoff (z_standoff = 0.4 m above the grasp) -> grasp (close) -> standoff -> ...
    - No re-perception and no success check in `try_executing_grasp`.
    - The place policy does re-observe: if the target is more than 38.5 cm away it moves forward and then re-estimates the placement point.

16. Liu et al. (2024). OK-Robot. arXiv 2401.12202. VERIFIED.
    - One head-camera RGB-D view feeds AnyGrasp and LangSam.
    - The open-loop approach follows waypoints p - 0.2a, p - 0.08a, p - 0.04a, p, slowing near the object so it does not knock light items.
    - Gripper closing is closed-loop on the grip itself.
    - The authors name open-loop trajectory collisions and missing error detection or retry as limits.

17. Boston Dynamics Spot SDK, `protos/bosdyn/api/manipulation_api.proto` and `robot_state.proto`. https://github.com/boston-dynamics/spot-sdk . VERIFIED (proto comments; the internal controller is not visible).
    - PickObjectInImage with WalkGazeMode PICK_AUTO_WALK_AND_GAZE walks to the object and centres it in the hand camera before planning.
    - MANIP_STATE_GRASP_PLANNING_WAITING_DATA_AT_EDGE refuses to plan while the target is at the image edge.
    - States reported: MANIP_STATE_GRASP_SUCCEEDED, MANIP_STATE_GRASP_FAILED, MANIP_STATE_GRASP_PLANNING_NO_SOLUTION, MANIP_STATE_GRASP_FAILED_TO_RAYCAST_INTO_MAP.
    - After the grasp: `is_gripper_holding_item` and `gripper_open_percentage`.

## D. Bounding blind motion

18. Will & Grossman (1975). An experimental system for computer controlled mechanical assembly. IEEE Trans. Computers C-24(9).
    URL fetched: https://www.cs.jhu.edu/~rht/Miscellaneous%20Materials/IBM%20Mechanical%20Assembler.pdf. VERIFIED.
    - Defines the guarded move: move until an expected sensory event occurs.
    - Each sensor gets [lower, upper] expected limits. Motion is allowed only while every sensor flag stays clear. A violation branches to a handler.
    - They guarded every move, even a retract to a supposedly clear position.

## Synthesis (common proven pattern)

- **A blind final segment is the accepted norm for static targets.** DGBench calls the conventional wrist mount suitable for static grasping and says closed-loop systems revert to open loop in the final phase. GG-CNN's blind segment (~70 mm gripper-to-object, after freezing at 150 mm camera depth) is almost the same length as our 71 mm descent. Viereck uses a predefined final motion below 14 cm.
- **Freeze the last good estimate, filtered, at a pre-set distance threshold.** GG-CNN averages 3 frames. Haviland uses the last valid depth frame. Folio initialises from the last measurement. Confirm alignment at the hover pose and freeze it before descending. Use several frames and a stability check, not a single frame.
- **During the blind part, run toward the frozen target with proprioception or own commands.** Do not re-plan. Folio & Cadenat show the error then comes from velocity and command drift and from timing uncertainty, so log the command history and sampling time.
- **Guard the blind move.** Use a z-floor, an "at goal" check and a contact/force threshold (GG-CNN: z < 0.01, z - 0.01 < goal, Fz < -5 N; GG-CNN open-loop and Spot also stop on force). Guarded-move semantics (Will & Grossman) mean preset sensor limits stop motion and branch to a handler.
- **Get the pose for a monocular RGB, known-height target by ray-plane intersection.** This is Burgess-Limerick's method and fits a floor beam of known height.
- **Gate entry into the blind phase on target quality.** Spot will not plan while the target is at the image edge. Stretch VS uses an error < 2 cm gate. Pre-shape the gripper width while the target is still visible (GG-CNN).
- **Verify after the grasp, then lift or retry.** Checks seen: fingers not fully closed (Levine, gripper reading > 1 cm), effort plus fingertip-gap window (Stretch VS), holding flag (Spot), lift test (GG-CNN, QT-Opt), image drop test. Re-observe after a base displacement (HomeRobot place: move if > 38.5 cm, then re-estimate). stretch_ros grasp_object shows what happens without verification: it always reports success.
- **Honest gap: no source has an explicit time limit on the blind phase or a taxonomy of abort codes.** Precedents are distance-based freeze thresholds (150 mm / 14 cm / 25 cm / 0.1 m), force and z guards, and loop counters (Stretch VS: retract capped at 60 cycles, `frames_since_toy_detected`). Explicit blind distance and time limits with abort codes are our own addition, justified by guarded-move semantics. Mark them as our design, not borrowed.
