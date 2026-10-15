# search27 rejection table

Source 38dbd82e7ea5872452435c8142f9bf17e6534d7c; raw /home/ugrp/ugrp-sim/runs/search27-r3-short6-38dbd82e

Reproduce: `cd /home/ugrp/ugrp-sim/src/38dbd82e7ea5872452435c8142f9bf17e6534d7c && .venv-sim/bin/python /home/ugrp/ugrp-sim/outputs/search27-report.py /home/ugrp/ugrp-sim/runs/search27-r3-short6-38dbd82e /home/ugrp/ugrp-sim/outputs/search27-r3-report`

|gate|pass|reject|
|---|---:|---:|
|planned|6|None|
|started|6|0|
|final_complete|5|1|
|not_cap_end|4|1|
|physical_success|2|2|

Reason distribution (passes separate in JSON):
- blocked_goal: 6214
- endpoint_feasible: 3042
- unsafe_body_sweep: 2146
- first_command_invalid: 245
- blocked_retreat: 130
- planning_budget: 53
- feasible: 15
- budget_incomplete: 1

## episode 0 / 315709 / off: cap_end

candidate_funnels
```json
{"endpoint": {"N": 612, "funnel": [{"gate": "entered", "cumulative_pass": 612, "rejected_here": null}, {"gate": "IRM", "cumulative_pass": 612, "rejected_here": 0}, {"gate": "jaw", "cumulative_pass": 612, "rejected_here": 0}, {"gate": "bounds", "cumulative_pass": 612, "rejected_here": 0}, {"gate": "goal", "cumulative_pass": 469, "rejected_here": 143}, {"gate": "retreat", "cumulative_pass": 352, "rejected_here": 117}, {"gate": "view", "cumulative_pass": 352, "rejected_here": 0}, {"gate": "pick_arm", "cumulative_pass": 351, "rejected_here": 1}, {"gate": "endpoint", "cumulative_pass": 351, "rejected_here": 0}]}, "full": {"N": 121, "funnel": [{"gate": "entered", "cumulative_pass": 121, "rejected_here": null}, {"gate": "IRM", "cumulative_pass": 121, "rejected_here": 0}, {"gate": "jaw", "cumulative_pass": 121, "rejected_here": 0}, {"gate": "bounds", "cumulative_pass": 121, "rejected_here": 0}, {"gate": "goal", "cumulative_pass": 121, "rejected_here": 0}, {"gate": "retreat", "cumulative_pass": 121, "rejected_here": 0}, {"gate": "path", "cumulative_pass": 121, "rejected_here": 0}, {"gate": "body_path", "cumulative_pass": 121, "rejected_here": 0}, {"gate": "view", "cumulative_pass": 121, "rejected_here": 0}, {"gate": "pick_arm", "cumulative_pass": 121, "rejected_here": 0}, {"gate": "connector", "cumulative_pass": 121, "rejected_here": 0}, {"gate": "first_command", "cumulative_pass": 4, "rejected_here": 117}, {"gate": "feasible", "cumulative_pass": 4, "rejected_here": 0}]}}
```
frame_funnel
```json
[{"gate": "input_frames", "cumulative_pass": 1200, "rejected_here": null}, {"gate": "label_written", "cumulative_pass": 1200, "rejected_here": 0}, {"gate": "approach_align_ready", "cumulative_pass": 852, "rejected_here": 348}, {"gate": "band_visible", "cumulative_pass": 838, "rejected_here": 14}, {"gate": "band_admitted", "cumulative_pass": 838, "rejected_here": 0}]
```
event_funnel
```json
[{"gate": "events", "cumulative_pass": 128, "rejected_here": null}, {"gate": "any_endpoint_prefix_pass", "cumulative_pass": 128, "rejected_here": 0}, {"gate": "any_complete_pass", "cumulative_pass": 4, "rejected_here": 124}]
```

## episode 1 / 315709 / cargo_v6: teacher_failure

candidate_funnels
```json
{"endpoint": {"N": 273, "funnel": [{"gate": "entered", "cumulative_pass": 273, "rejected_here": null}, {"gate": "IRM", "cumulative_pass": 273, "rejected_here": 0}, {"gate": "jaw", "cumulative_pass": 273, "rejected_here": 0}, {"gate": "bounds", "cumulative_pass": 273, "rejected_here": 0}, {"gate": "goal", "cumulative_pass": 195, "rejected_here": 78}, {"gate": "retreat", "cumulative_pass": 182, "rejected_here": 13}, {"gate": "view", "cumulative_pass": 182, "rejected_here": 0}, {"gate": "pick_arm", "cumulative_pass": 182, "rejected_here": 0}, {"gate": "endpoint", "cumulative_pass": 182, "rejected_here": 0}]}, "full": {"N": 3, "funnel": [{"gate": "entered", "cumulative_pass": 3, "rejected_here": null}, {"gate": "IRM", "cumulative_pass": 3, "rejected_here": 0}, {"gate": "jaw", "cumulative_pass": 3, "rejected_here": 0}, {"gate": "bounds", "cumulative_pass": 3, "rejected_here": 0}, {"gate": "goal", "cumulative_pass": 3, "rejected_here": 0}, {"gate": "retreat", "cumulative_pass": 3, "rejected_here": 0}, {"gate": "path", "cumulative_pass": 3, "rejected_here": 0}, {"gate": "body_path", "cumulative_pass": 3, "rejected_here": 0}, {"gate": "view", "cumulative_pass": 3, "rejected_here": 0}, {"gate": "pick_arm", "cumulative_pass": 3, "rejected_here": 0}, {"gate": "connector", "cumulative_pass": 3, "rejected_here": 0}, {"gate": "first_command", "cumulative_pass": 3, "rejected_here": 0}, {"gate": "feasible", "cumulative_pass": 3, "rejected_here": 0}]}}
```
frame_funnel
```json
[{"gate": "input_frames", "cumulative_pass": 944, "rejected_here": null}, {"gate": "label_written", "cumulative_pass": 944, "rejected_here": 0}, {"gate": "approach_align_ready", "cumulative_pass": 721, "rejected_here": 223}, {"gate": "band_visible", "cumulative_pass": 707, "rejected_here": 14}, {"gate": "band_admitted", "cumulative_pass": 707, "rejected_here": 0}]
```
event_funnel
```json
[{"gate": "events", "cumulative_pass": 6, "rejected_here": null}, {"gate": "any_endpoint_prefix_pass", "cumulative_pass": 6, "rejected_here": 0}, {"gate": "any_complete_pass", "cumulative_pass": 3, "rejected_here": 3}]
```

## episode 2 / 8311709 / off: teacher_failure

candidate_funnels
```json
{"endpoint": {"N": 4186, "funnel": [{"gate": "entered", "cumulative_pass": 4186, "rejected_here": null}, {"gate": "IRM", "cumulative_pass": 4186, "rejected_here": 0}, {"gate": "jaw", "cumulative_pass": 4186, "rejected_here": 0}, {"gate": "bounds", "cumulative_pass": 4186, "rejected_here": 0}, {"gate": "goal", "cumulative_pass": 1196, "rejected_here": 2990}, {"gate": "retreat", "cumulative_pass": 1196, "rejected_here": 0}, {"gate": "view", "cumulative_pass": 1196, "rejected_here": 0}, {"gate": "pick_arm", "cumulative_pass": 1196, "rejected_here": 0}, {"gate": "endpoint", "cumulative_pass": 1196, "rejected_here": 0}]}, "full": {"N": 1084, "funnel": [{"gate": "entered", "cumulative_pass": 1084, "rejected_here": null}, {"gate": "IRM", "cumulative_pass": 1084, "rejected_here": 0}, {"gate": "jaw", "cumulative_pass": 1084, "rejected_here": 0}, {"gate": "bounds", "cumulative_pass": 1084, "rejected_here": 0}, {"gate": "goal", "cumulative_pass": 1084, "rejected_here": 0}, {"gate": "retreat", "cumulative_pass": 1084, "rejected_here": 0}, {"gate": "path", "cumulative_pass": 1084, "rejected_here": 0}, {"gate": "body_path", "cumulative_pass": 4, "rejected_here": 1080}, {"gate": "view", "cumulative_pass": 4, "rejected_here": 0}, {"gate": "pick_arm", "cumulative_pass": 4, "rejected_here": 0}, {"gate": "connector", "cumulative_pass": 4, "rejected_here": 0}, {"gate": "first_command", "cumulative_pass": 4, "rejected_here": 0}, {"gate": "feasible", "cumulative_pass": 4, "rejected_here": 0}]}}
```
frame_funnel
```json
[{"gate": "input_frames", "cumulative_pass": 660, "rejected_here": null}, {"gate": "label_written", "cumulative_pass": 660, "rejected_here": 0}, {"gate": "approach_align_ready", "cumulative_pass": 631, "rejected_here": 29}, {"gate": "band_visible", "cumulative_pass": 617, "rejected_here": 14}, {"gate": "band_admitted", "cumulative_pass": 617, "rejected_here": 0}]
```
event_funnel
```json
[{"gate": "events", "cumulative_pass": 1130, "rejected_here": null}, {"gate": "any_endpoint_prefix_pass", "cumulative_pass": 1130, "rejected_here": 0}, {"gate": "any_complete_pass", "cumulative_pass": 4, "rejected_here": 1126}]
```

## episode 3 / 8311709 / cargo_v6: supervisor_stop

candidate_funnels
```json
{"endpoint": {"N": 4368, "funnel": [{"gate": "entered", "cumulative_pass": 4368, "rejected_here": null}, {"gate": "IRM", "cumulative_pass": 4368, "rejected_here": 0}, {"gate": "jaw", "cumulative_pass": 4368, "rejected_here": 0}, {"gate": "bounds", "cumulative_pass": 4368, "rejected_here": 0}, {"gate": "goal", "cumulative_pass": 1365, "rejected_here": 3003}, {"gate": "retreat", "cumulative_pass": 1365, "rejected_here": 0}, {"gate": "view", "cumulative_pass": 1365, "rejected_here": 0}, {"gate": "pick_arm", "cumulative_pass": 1365, "rejected_here": 0}, {"gate": "endpoint", "cumulative_pass": 1365, "rejected_here": 0}]}, "full": {"N": 1199, "funnel": [{"gate": "entered", "cumulative_pass": 1199, "rejected_here": null}, {"gate": "IRM", "cumulative_pass": 1199, "rejected_here": 0}, {"gate": "jaw", "cumulative_pass": 1199, "rejected_here": 0}, {"gate": "bounds", "cumulative_pass": 1199, "rejected_here": 0}, {"gate": "goal", "cumulative_pass": 1199, "rejected_here": 0}, {"gate": "retreat", "cumulative_pass": 1199, "rejected_here": 0}, {"gate": "path", "cumulative_pass": 1199, "rejected_here": 0}, {"gate": "body_path", "cumulative_pass": 133, "rejected_here": 1066}, {"gate": "view", "cumulative_pass": 133, "rejected_here": 0}, {"gate": "pick_arm", "cumulative_pass": 132, "rejected_here": 1}, {"gate": "connector", "cumulative_pass": 132, "rejected_here": 0}, {"gate": "first_command", "cumulative_pass": 4, "rejected_here": 128}, {"gate": "feasible", "cumulative_pass": 4, "rejected_here": 0}]}}
```
frame_funnel
```json
[{"gate": "input_frames", "cumulative_pass": 762, "rejected_here": null}, {"gate": "label_written", "cumulative_pass": 754, "rejected_here": 8}, {"gate": "approach_align_ready", "cumulative_pass": 595, "rejected_here": 159}, {"gate": "band_visible", "cumulative_pass": 581, "rejected_here": 14}, {"gate": "band_admitted", "cumulative_pass": 581, "rejected_here": 0}]
```
event_funnel
```json
[{"gate": "events", "cumulative_pass": 1247, "rejected_here": null}, {"gate": "any_endpoint_prefix_pass", "cumulative_pass": 1247, "rejected_here": 0}, {"gate": "any_complete_pass", "cumulative_pass": 4, "rejected_here": 1243}]
```

## episode 4 / 8312300 / off: success

candidate_funnels
```json
{}
```
frame_funnel
```json
[{"gate": "input_frames", "cumulative_pass": 452, "rejected_here": null}, {"gate": "label_written", "cumulative_pass": 452, "rejected_here": 0}, {"gate": "approach_align_ready", "cumulative_pass": 292, "rejected_here": 160}, {"gate": "band_visible", "cumulative_pass": 285, "rejected_here": 7}, {"gate": "band_admitted", "cumulative_pass": 285, "rejected_here": 0}]
```
event_funnel
```json
[{"gate": "events", "cumulative_pass": 0, "rejected_here": null}, {"gate": "any_endpoint_prefix_pass", "cumulative_pass": 0, "rejected_here": 0}, {"gate": "any_complete_pass", "cumulative_pass": 0, "rejected_here": 0}]
```

## episode 5 / 8312300 / cargo_v6: success

candidate_funnels
```json
{}
```
frame_funnel
```json
[{"gate": "input_frames", "cumulative_pass": 454, "rejected_here": null}, {"gate": "label_written", "cumulative_pass": 454, "rejected_here": 0}, {"gate": "approach_align_ready", "cumulative_pass": 294, "rejected_here": 160}, {"gate": "band_visible", "cumulative_pass": 287, "rejected_here": 7}, {"gate": "band_admitted", "cumulative_pass": 287, "rejected_here": 0}]
```
event_funnel
```json
[{"gate": "events", "cumulative_pass": 0, "rejected_here": null}, {"gate": "any_endpoint_prefix_pass", "cumulative_pass": 0, "rejected_here": 0}, {"gate": "any_complete_pass", "cumulative_pass": 0, "rejected_here": 0}]
```
