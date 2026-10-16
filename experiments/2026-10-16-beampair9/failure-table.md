# 실패9 / cap_end6 원본별 표

|시드|종료 분류|로봇별 종료|가장 많은 기록 검사|막은 물체|해당 검사 최소 틈 m|
|---|---|---|---|---|---:|
|8328015|teacher_failure|r1:alignment_no_progress; r2:episode_timeout|alignment_no_progress|none:non_geometric_terminal|N/A (비기하)|
|8328010|teacher_failure|r1:approach_blocked_handoff; r2:peer_approach_handoff|memory_margin|zone_wall_divider_1|0.03576906516466032|
|8328036|teacher_failure|r1:search_timeout_handoff; r2:peer_search_handoff|search_timeout_handoff|none:non_geometric_terminal|N/A (비기하)|
|8328038|teacher_failure|r1:approach_blocked_handoff; r2:peer_approach_handoff|memory_margin|zone_wall_south|0.042490707270716264|
|8328052|cap_end:sim_cap|r1:episode_timeout; r2:episode_timeout|cap_end|none:cap_end|N/A (비기하)|
|8328061|teacher_failure|r1:no_stable_joint_hold_3s; r2:no_stable_joint_hold_3s|no_stable_joint_hold_3s|none:non_geometric_terminal|N/A (비기하)|
|8328068|teacher_failure|r1:peer_approach_handoff; r2:approach_blocked_handoff|memory_margin|cyan_1|0.01029875380687914|
|8328122|cap_end:sim_cap|r1:episode_timeout; r2:episode_timeout|peer_goal|r3|-0.07612877348195385|
|8328128|cap_end:sim_cap|r1:episode_timeout; r2:episode_timeout|peer_goal|r1|-0.07051497279260283|
|8328168|teacher_failure|r1:peer_approach_handoff; r2:approach_blocked_handoff|memory_margin|zone_wall_north|0.0061072837520137965|
|8328183|teacher_failure|r1:peer_approach_handoff; r2:approach_blocked_handoff|current_geometry|cyan_1|-0.035740852297878795|
|8328195|cap_end:sim_cap|r1:episode_timeout; r2:episode_timeout|peer_goal|r3|-0.007166084468170575|
|8328152|teacher_failure|r1:approach_blocked_handoff; r2:peer_approach_handoff|current_geometry|red_1|-0.035740852297878795|
|8328198|cap_end:sim_cap|r1:episode_timeout; r2:episode_timeout|cap_end|none:cap_end|N/A (비기하)|
|8328188|cap_end:wall_planning_safety|r1:None; r2:None|current_geometry|cyan_1|-0.035740852297878795|

검사 빈도/최소 틈은 기록된 후보 검사이며 종료의 원인과 자동으로 동일시하지 않는다. None은 비기하 종료/검사에서 적용할 틈이 없음을 뜻한다. 실제 상자 겹침 확인2개는 static-census.json에 별도로 있다.

관문40 r1 역할 청록19/파랑21, 기록200 청록92/파랑108. 거부 루프의 end 변수 누출을 새 기본off 배치 모드에서 수정했다. 기존 데이터/계획에는 소급 적용하지 않았다.
