# PR406 reuse for egomap41

Source: `codex/s2-realism`, commit `2fa4bf9a0e8097bcd4d1e1933b7d04e4d54dd965`.
`provenance.json` records exact source files, line intervals, source and copied
definition hashes. Function/class/constant bodies are copied unchanged; imports
are narrowed and the S2 Runtime/controller is omitted. No #406 file was edited.

The repository's existing algorithm ports cite Nav2 AMCL
`235fc5ce55bdf94d9be360fdbca39d89dc0e4f74` (LGPL-2.1-or-later), ROS navigation
`f44bb1fc` selective resampling, and Fox 2001 KLD-Sampling equation 7.
These Python bodies reuse the UGRP port, not a newly fetched ROS implementation.
Upstream algorithm attribution and scope comments are retained in the copied
definitions. New grid/recording adapters are separate in `self_map_relocalize.py`.
No new external library or venv is required.

## egomap42 landmarks

Source `6a9e93f1a463ed2e356b044487c6b025ad018b63` (PR406):
`zone_solo_cyan_landmarks.py` detector, MapFeatures and likelihood definitions;
`zone_solo_cyan_visibility.py` geometric shadow primitives and dedented
`Visibility.depth_image`; `zone_solo_cyan_scene_change.py` cyan mask function.
All selected bodies and constants are unchanged, with line numbers and hashes
in provenance.json. No S2 Runtime, active controller, or prior visibility veto
is imported. `self_map_landmark_sensor.py` supplies egomap34 command-FK camera,
frozen measured wall columns and the original clear/cargo-mask formula.
`self_map_causal.py` supplies only previously observed partial segments/doors in
the own frame; it does not manufacture whole colored rectangles. Each past
observation is an alternative in the original maximum-likelihood association,
not an extra factor. The fixed Gaussian noise is unchanged (memory covariance
is provenance only). Shared geometry/color dependency hashes are sealed by
the experiment runner. No #406 source file or environment was modified.
