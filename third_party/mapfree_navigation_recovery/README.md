# Nav2 recovery references

Pinned navigation2 revision `235fc5ce55bdf94d9be360fdbca39d89dc0e4f74`.
Original files and Apache-2.0 notices are retained byte for byte; see SOURCES.json.
`harness/public_navigation_recovery.py` ports the BT contextual clear, six retries,
clear/spin/wait/backup ordering and RPP curvature/carrot projection. The upstream ROS
servers/BT engine, acceleration integrator and rate scheduler are **not executed**.
UGRP keeps 10Hz command tracking, .5rad/s spin and .24m curvature radius for this
robot, 2s own-camera settling between 1s actions, M1 command saturation, own DR.
The static and observation layers share a 2D grid; clear preserves static obstacles
and restores current sensor observations. All departures from full Nav2 are explicit.
