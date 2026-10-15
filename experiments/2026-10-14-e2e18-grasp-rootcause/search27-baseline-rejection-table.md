# search26 comparison diagnostic: separate scenes

Source f92b07aa869dc3b960d22adb69c01f2b9b8c9eeb; raw /home/ugrp/ugrp-sim/runs/search26-comparison32-f92b07aa; reproduce: `cd /home/ugrp/ugrp-sim/src/f92b07aa869dc3b960d22adb69c01f2b9b8c9eeb && PYTHONPATH=. .venv-sim/bin/python /home/ugrp/ugrp-sim/outputs/search26-comparison32-analyze.py`

## off

success 5/8 final; planned 16; failure 3; cap_end 0; supervisor_stop 8

run_funnel

|gate|cumulative pass|rejected here|
|---|---:|---:|
|planned|16|None|
|started|16|0|
|final_complete|8|8|
|not_HOST_ERROR|8|0|
|not_cap_end|8|0|
|joint_hold_success|5|3|

frame_funnel

|gate|cumulative pass|rejected here|
|---|---:|---:|
|robot_input_frames|6970|None|
|label_written|6946|24|
|approach_align_ready|5193|1753|
|assigned_band_visible|5018|175|
|assigned_band_measurement_admitted|5018|0|

event_funnel

|gate|cumulative pass|rejected here|
|---|---:|---:|
|candidate_events|248|None|
|nonempty|248|0|
|any_endpoint_pass|6|242|
|any_full_pass|6|0|

alignment_candidate_funnel

|gate|cumulative pass|rejected here|
|---|---:|---:|
|axis_pulse_checks|372|None|
|body_and_arm_safety|364|8|
|nonzero_and_merit_or_IK_recovery|359|5|
|selected_one_per_tick|129|230|
|issued_after_final_safety|129|0|

Candidate terminal reason counts (includes passes; largest first)

|reason|N|
|---|---:|
|blocked_goal|13858|
|unsafe_body_sweep|8489|
|endpoint_feasible|215|
|feasible|6|

Final command rejects

|reason|blocker|N|
|---|---|---:|
|body_sweep_reject|band_blue|71|

## cargo_v6

success 5/8 final; planned 16; failure 2; cap_end 1; supervisor_stop 8

run_funnel

|gate|cumulative pass|rejected here|
|---|---:|---:|
|planned|16|None|
|started|16|0|
|final_complete|8|8|
|not_HOST_ERROR|8|0|
|not_cap_end|7|1|
|joint_hold_success|5|2|

frame_funnel

|gate|cumulative pass|rejected here|
|---|---:|---:|
|robot_input_frames|6814|None|
|label_written|6802|12|
|approach_align_ready|5021|1781|
|assigned_band_visible|4846|175|
|assigned_band_measurement_admitted|4846|0|

event_funnel

|gate|cumulative pass|rejected here|
|---|---:|---:|
|candidate_events|94|None|
|nonempty|94|0|
|any_endpoint_pass|5|89|
|any_full_pass|5|0|

alignment_candidate_funnel

|gate|cumulative pass|rejected here|
|---|---:|---:|
|axis_pulse_checks|402|None|
|body_and_arm_safety|402|0|
|nonzero_and_merit_or_IK_recovery|396|6|
|selected_one_per_tick|138|258|
|issued_after_final_safety|138|0|

Candidate terminal reason counts (includes passes; largest first)

|reason|N|
|---|---:|
|blocked_goal|6721|
|unsafe_body_sweep|1599|
|endpoint_feasible|216|
|blocked_retreat|13|
|feasible|5|

Final command rejects

|reason|blocker|N|
|---|---|---:|
|body_sweep_reject|band_blue|6|


## off true candidate rejections (passes excluded)

|reason|N|
|---|---:|
|blocked_goal|13858|
|unsafe_body_sweep|8489|

## cargo_v6 true candidate rejections (passes excluded)

|reason|N|
|---|---:|
|blocked_goal|6721|
|unsafe_body_sweep|1599|
|blocked_retreat|13|

Stopped/failed gate per episode

|episode|scene|category|stopped at|
|---|---|---|---|
|episode-000|cargo_v6|cap_end|planning_wall_safety_cap_unknown_candidate_stage|
|episode-001|off|teacher_failure|final_command_body_safety|
|episode-004|off|teacher_failure|candidate_endpoint_geometry|
|episode-005|cargo_v6|teacher_failure|candidate_endpoint_geometry|
|episode-006|off|teacher_failure|approach_progress_recovery_handoff|
|episode-007|cargo_v6|teacher_failure|approach_progress_recovery_handoff|
|episode-016|off|supervisor_stop|operator_supervisor_stop_during_approach|
|episode-017|cargo_v6|supervisor_stop|operator_supervisor_stop_during_approach|
|episode-018|off|supervisor_stop|operator_supervisor_stop_during_approach|
|episode-019|cargo_v6|supervisor_stop|operator_supervisor_stop_during_approach|
|episode-020|off|supervisor_stop|operator_supervisor_stop_during_approach,ready|
|episode-021|cargo_v6|supervisor_stop|operator_supervisor_stop_during_approach,ready|
|episode-022|off|supervisor_stop|operator_supervisor_stop_during_align,ready|
|episode-023|cargo_v6|supervisor_stop|operator_supervisor_stop_during_align,ready|
|episode-024|off|supervisor_stop|operator_supervisor_stop_during_approach|
|episode-025|cargo_v6|supervisor_stop|operator_supervisor_stop_during_approach|
|episode-026|off|supervisor_stop|operator_supervisor_stop_during_approach,ready|
|episode-027|cargo_v6|supervisor_stop|operator_supervisor_stop_during_approach,ready|
|episode-028|off|supervisor_stop|operator_supervisor_stop_during_approach|
|episode-029|cargo_v6|supervisor_stop|operator_supervisor_stop_during_approach|
|episode-030|off|supervisor_stop|operator_supervisor_stop_during_approach|
|episode-031|cargo_v6|supervisor_stop|operator_supervisor_stop_during_approach|
