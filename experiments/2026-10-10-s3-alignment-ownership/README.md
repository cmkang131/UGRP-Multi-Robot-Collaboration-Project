# s3fix16: endpoint visibility, command ownership and coarse servo

2026-10-10. DEV development round, not confirmation. Mac physics/render/replay forbidden;
all replay and physics on `host=oracle-x86`. PR #416 remains draft; no merge/CI wait.

## Before diagnosis

A is classified from s3fix15 original raw, per `beam_obs` timestamp: exact saved
MuJoCo camera pose and qpos, nearest grip-band top centre + four corners projected
into the actual rendered pinhole support (raw fisheye remap cannot restore missing
pinhole pixels). `fov_clipped` means at least one corner is outside support;
`in_fov_rejected` means all corners inside, not proof of absence of occlusion.
No physics step, no image regeneration, no GT enters controller.
Raw: `outputs/oracle-runs/s3fix15-batch-r1/cohort/`; archived source
`4e19382d59a9bb2bbf351a7fca1356cdf480e8a0`.
If FOV loss: freeze own RGB measurement before loss and use only issued-command
calibration in a bounded final open-loop segment. If in-FOV rejection: fix only
the identified detector cause. B: fine alignment owns arm commands exclusively,
PF measured calibration unchanged. C: retain s3fix15 acceptance widths, require
single-axis immediate progress with move-settle-look and hysteresis.
Full 10-case manifest will be committed before physics; no midbatch adaptation.

## References

- Hutchinson, Hager, Corke (1996), [A Tutorial on Visual Servo Control](https://faculty.cc.gatech.edu/~seth/ResPages/pdfs/HutHagCor96.pdf): position/image visual feedback and look-then-move architecture.
- [ROS2 control command ownership](https://docs.universal-robots.com/Universal_Robots_ROS_Documentation/rolling/doc/ur_robot_driver/ur_robot_driver/doc/usage/controllers.html): one active controller per claimed command interface; explicit handover.
