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
